"""
src/portfolio/positions/position_manager.py

Position lifecycle management with VALR spot trading integration.

Helios V3.0 - Tier 5: Guardian Portfolio Manager
Phase 5, Week 23: Position Lifecycle Manager

Updated: January 2025
- Integrated VALR spot trading flow (limit entry → wait → limit SL/TP)
- Added order fill monitoring with timeout/partial fill handling
- Exchange-native SL/TP order placement for spot pairs
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from enum import Enum
import logging
import asyncio

from config.trading_config import get_spot_trading_config

logger = logging.getLogger(__name__)


class PositionStatus(Enum):
    """Position status values."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIMEOUT = "TIMEOUT"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"


class PositionManager:
    """
    Manage position lifecycle.

    Responsibilities:
    - Open positions (execute orders via VALR)
    - Monitor positions (P&L, SL/TP triggers)
    - Update positions (trailing stops)
    - Close positions (SL/TP/timeout/manual)
    """

    def __init__(self, db_session: AsyncSession, trading_client=None):
        """
        Initialize Position Manager.

        Args:
            db_session: Database session for queries
            trading_client: VALR trading client for order execution (optional for testing)
        """
        self.db = db_session
        self.trading_client = trading_client
        logger.info("PositionManager initialized")

    async def open_position(
        self,
        pair: str,
        signal: str,
        trade_params: Dict,
        strategic_reasoning: str,
        trading_mode: str = "PAPER"
    ) -> Dict:
        """
        Open a new position with VALR spot trading flow - MODE-AWARE.

        Flow for LIVE mode:
        1. Place LIMIT BUY order at market price (for fast fill + price protection)
        2. Wait for order to fill (with timeout and partial fill handling)
        3. Once filled, place TWO LIMIT SELL orders on exchange (TP and SL)
        4. Record position with all order IDs in database

        Flow for PAPER mode:
        1. Simulate limit order execution
        2. Simulate SL/TP order placement
        3. Record position in database

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: 'BUY' or 'SELL'
            trade_params: Dict with position_size_zar, leverage, stop_loss_pct, take_profit_pct
            strategic_reasoning: LLM reasoning for this trade
            trading_mode: "PAPER" or "LIVE"

        Returns:
            Dict with success, position_id, entry_price, entry_order_id, tp_order_id, sl_order_id
        """
        config = get_spot_trading_config()

        logger.info(f"Opening {signal} position for {pair} with size R{trade_params['position_size_zar']:,.2f} ({trading_mode} mode)")

        # Step 1: Get current market price
        current_price = await self._get_current_price(pair)
        if current_price == 0.0:
            logger.error(f"Cannot get current price for {pair}")
            return {
                'success': False,
                'error': f'Cannot get current price for {pair}'
            }

        # Calculate quantity
        quantity = trade_params['position_size_zar'] / current_price

        # Determine order side
        order_side = 'BUY' if signal == 'BUY' else 'SELL'

        # Step 2: Place entry order (LIMIT for price protection)
        entry_price = current_price * (1 + config.limit_order_price_offset_pct / 100.0)
        entry_order_id = None
        filled_quantity = quantity
        fill_status = "FILLED"

        if self.trading_client:
            try:
                logger.info(f"Placing LIMIT {order_side} order: {quantity:.8f} @ R{entry_price:,.0f}")

                # Place limit order
                order_result = await self.trading_client.place_limit_order(
                    pair=pair,
                    side=order_side,
                    quantity=quantity,
                    price=entry_price
                )

                if not order_result.get('success'):
                    logger.error(f"Entry order failed: {order_result.get('error')}")
                    return {
                        'success': False,
                        'error': order_result.get('error')
                    }

                entry_order_id = order_result.get('orderId') or order_result.get('id')
                logger.info(f"Entry order placed: {entry_order_id}")

                # Step 3: Wait for order to fill
                fill_result = await self._wait_for_fill(
                    order_id=entry_order_id,
                    pair=pair,
                    timeout_seconds=config.order_timeout_seconds
                )

                if fill_result['status'] == 'TIMEOUT':
                    logger.warning(f"Entry order timeout after {config.order_timeout_seconds}s")

                    if config.cancel_on_timeout:
                        try:
                            await self.trading_client.cancel_order(pair, entry_order_id)
                            logger.info("Unfilled entry order cancelled")
                        except Exception as e:
                            logger.warning(f"Could not cancel order: {e}")

                    return {
                        'success': False,
                        'error': 'Order did not fill within timeout period'
                    }

                elif fill_result['status'] == 'PARTIAL':
                    if config.accept_partial_fills:
                        logger.info(f"Accepting partial fill: {fill_result['filled_quantity']:.8f}")
                        filled_quantity = fill_result['filled_quantity']
                        entry_price = fill_result['fill_price']
                        fill_status = "PARTIAL"

                        # Cancel remaining
                        try:
                            await self.trading_client.cancel_order(pair, entry_order_id)
                        except Exception as e:
                            logger.warning(f"Could not cancel remaining: {e}")
                    else:
                        logger.warning("Partial fill not accepted, cancelling order")
                        try:
                            await self.trading_client.cancel_order(pair, entry_order_id)
                        except:
                            pass
                        return {
                            'success': False,
                            'error': 'Order partially filled, but partial fills not accepted'
                        }

                else:  # FILLED
                    filled_quantity = fill_result['filled_quantity']
                    entry_price = fill_result['fill_price']
                    logger.info(f"Entry order filled: {filled_quantity:.8f} @ R{entry_price:,.2f}")

            except Exception as e:
                logger.error(f"Entry order error: {e}")
                return {
                    'success': False,
                    'error': str(e)
                }
        else:
            # Paper trading mode - simulate fill
            logger.info(f"PAPER: Simulating {order_side} fill at R{entry_price:,.2f}")
            entry_order_id = f"PAPER_ENTRY_{datetime.utcnow().timestamp()}"

        entry_time = datetime.utcnow()

        # Step 4: Record position in database
        position_id = await self._create_position_record(
            pair=pair,
            signal=signal,
            entry_price=entry_price,
            entry_time=entry_time,
            quantity=filled_quantity,
            trade_params=trade_params,
            strategic_reasoning=strategic_reasoning,
            order_id=entry_order_id,
            trading_mode=trading_mode,
            entry_order_status=fill_status
        )

        # Step 5: Place SL/TP orders on exchange (if configured)
        tp_order_id = None
        sl_order_id = None

        if config.place_sl_tp_on_exchange:
            sl_tp_result = await self._set_stop_loss_take_profit(
                position_id=position_id,
                pair=pair,
                signal=signal,
                entry_price=entry_price,
                quantity=filled_quantity,
                stop_loss_pct=trade_params['stop_loss_pct'],
                take_profit_pct=trade_params['take_profit_pct']
            )

            tp_order_id = sl_tp_result.get('tp_order_id')
            sl_order_id = sl_tp_result.get('sl_order_id')

        logger.info(f"Position opened: ID={position_id}, entry={entry_price:,.2f}, TP={tp_order_id}, SL={sl_order_id}")

        return {
            'success': True,
            'position_id': position_id,
            'pair': pair,
            'signal': signal,
            'entry_price': entry_price,
            'quantity': filled_quantity,
            'entry_order_id': entry_order_id,
            'tp_order_id': tp_order_id,
            'sl_order_id': sl_order_id,
            'fill_status': fill_status
        }

    async def monitor_positions(self, price_cache_getter=None) -> List[Dict]:
        """
        Monitor all open positions for SL/TP triggers.

        Called every 5 seconds by autonomous trading loop.

        Args:
            price_cache_getter: Optional callable to get real-time cached price
                               Should accept pair (str) and return price (float) or None

        Returns:
            List of positions that need action (close triggers)
        """
        # Get all open positions
        query = text("""
            SELECT
                id, pair, signal, entry_price, quantity,
                stop_loss_price, take_profit_price,
                entry_time, leverage
            FROM positions
            WHERE status = 'OPEN'
        """)

        result = await self.db.execute(query)
        rows = result.fetchall()

        actions = []

        for row in rows:
            position_id = row[0]
            pair = row[1]
            signal = row[2]
            entry_price = float(row[3])
            quantity = float(row[4])
            stop_loss_price = float(row[5]) if row[5] else None
            take_profit_price = float(row[6]) if row[6] else None
            entry_time = row[7]
            leverage = float(row[8])

            # Get current price (try cache first, fallback to database)
            current_price = await self._get_current_price(pair, price_cache_getter)

            # Calculate P&L
            if signal == 'BUY':
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # SELL
                pnl_pct = (entry_price - current_price) / entry_price

            pnl_pct *= leverage  # Apply leverage

            # Check stop loss
            if stop_loss_price:
                if (signal == 'BUY' and current_price <= stop_loss_price) or \
                   (signal == 'SELL' and current_price >= stop_loss_price):
                    logger.warning(f"Stop loss triggered for position {position_id} ({pair})")
                    actions.append({
                        'position_id': position_id,
                        'action': 'CLOSE',
                        'reason': 'STOP_LOSS',
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    })
                    continue

            # Check take profit
            if take_profit_price:
                if (signal == 'BUY' and current_price >= take_profit_price) or \
                   (signal == 'SELL' and current_price <= take_profit_price):
                    logger.info(f"Take profit triggered for position {position_id} ({pair})")
                    actions.append({
                        'position_id': position_id,
                        'action': 'CLOSE',
                        'reason': 'TAKE_PROFIT',
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    })
                    continue

            # Check timeout (close after 24 hours)
            time_open = datetime.utcnow() - entry_time
            if time_open > timedelta(hours=24):
                logger.info(f"Timeout triggered for position {position_id} ({pair}) - open for {time_open}")
                actions.append({
                    'position_id': position_id,
                    'action': 'CLOSE',
                    'reason': 'TIMEOUT',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct
                })
                continue

        if actions:
            logger.info(f"Monitor found {len(actions)} positions needing action")

        return actions

    async def close_position(
        self,
        position_id: int,
        reason: str,
        current_price: Optional[float] = None
    ) -> Dict:
        """
        Close a position.

        Args:
            position_id: Position ID to close
            reason: Reason for closing (STOP_LOSS, TAKE_PROFIT, TIMEOUT, MANUAL)
            current_price: Current market price (optional, will fetch if not provided)

        Returns:
            Dict with success, exit_price, pnl_pct, pnl_zar
        """
        logger.info(f"Closing position {position_id}, reason: {reason}")

        # Get position details
        query = text("""
            SELECT pair, signal, quantity, entry_price, leverage, tp_order_id
            FROM positions
            WHERE id = :position_id
        """)

        result = await self.db.execute(query, {'position_id': position_id})
        row = result.fetchone()

        if not row:
            logger.error(f"Position {position_id} not found")
            return {'success': False, 'error': 'Position not found'}

        pair = row[0]
        signal = row[1]
        quantity = float(row[2])
        entry_price = float(row[3])
        leverage = float(row[4])
        tp_order_id = row[5]

        # CRITICAL: Cancel TP order BEFORE closing position
        # If we close with market order while TP is active, we may not have enough BTC
        if self.trading_client and tp_order_id:
            try:
                logger.info(f"Cancelling TP order {tp_order_id} before closing position")
                await self.trading_client.cancel_order(pair, tp_order_id)
                logger.info(f"TP order cancelled successfully")
            except Exception as e:
                logger.warning(f"Could not cancel TP order: {e} - attempting close anyway")

        # Get current price if not provided
        if current_price is None:
            current_price = await self._get_current_price(pair)

        # Execute closing order (opposite side)
        close_side = 'SELL' if signal == 'BUY' else 'BUY'

        if self.trading_client:
            try:
                logger.info(f"Placing market {close_side} to close position: {quantity:.8f} {pair}")
                order_result = await self.trading_client.place_market_order(
                    pair=pair,
                    side=close_side,
                    quantity=quantity
                )

                if not order_result.get('success'):
                    logger.error(f"Close order failed: {order_result.get('error')}")
                    return {
                        'success': False,
                        'error': order_result.get('error')
                    }

                exit_price = order_result['fill_price']

            except Exception as e:
                logger.error(f"Close order error: {e}")
                return {
                    'success': False,
                    'error': str(e)
                }
        else:
            # Paper trading mode
            exit_price = current_price

        exit_time = datetime.utcnow()

        # Calculate final P&L
        if signal == 'BUY':
            pnl_pct = (exit_price - entry_price) / entry_price
            pnl_zar = (exit_price - entry_price) * quantity
        else:  # SELL
            pnl_pct = (entry_price - exit_price) / entry_price
            pnl_zar = (entry_price - exit_price) * quantity

        pnl_pct *= leverage
        pnl_zar *= leverage

        # Update position record
        update_query = text("""
            UPDATE positions
            SET
                status = :status,
                exit_price = :exit_price,
                exit_time = :exit_time,
                pnl_pct = :pnl_pct,
                pnl_zar = :pnl_zar,
                close_reason = :reason
            WHERE id = :position_id
        """)

        await self.db.execute(update_query, {
            'status': reason,
            'exit_price': exit_price,
            'exit_time': exit_time,
            'pnl_pct': pnl_pct,
            'pnl_zar': pnl_zar,
            'reason': reason,
            'position_id': position_id
        })
        await self.db.commit()

        # Update portfolio value
        await self._update_portfolio_value(pnl_zar)

        logger.info(f"Position {position_id} closed: P&L = R{pnl_zar:,.2f} ({pnl_pct:.2%})")

        return {
            'success': True,
            'position_id': position_id,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'pnl_zar': pnl_zar,
            'reason': reason
        }

    async def _create_position_record(
        self,
        pair: str,
        signal: str,
        entry_price: float,
        entry_time: datetime,
        quantity: float,
        trade_params: Dict,
        strategic_reasoning: str,
        order_id: str,
        trading_mode: str = "PAPER",
        entry_order_status: str = "FILLED"
    ) -> int:
        """Create position record in database - MODE-TAGGED with entry order status."""
        query = text("""
            INSERT INTO positions (
                pair, signal, entry_price, entry_time, quantity,
                position_value_zar, leverage,
                stop_loss_pct, take_profit_pct,
                strategic_reasoning, order_id,
                status, created_at, trading_mode, entry_order_status
            ) VALUES (
                :pair, :signal, :entry_price, :entry_time, :quantity,
                :position_value, :leverage,
                :stop_loss_pct, :take_profit_pct,
                :reasoning, :order_id,
                'OPEN', :created_at, :trading_mode, :entry_order_status
            )
            RETURNING id
        """)

        result = await self.db.execute(query, {
            'pair': pair,
            'signal': signal,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'quantity': quantity,
            'position_value': trade_params['position_size_zar'],
            'leverage': trade_params['leverage'],
            'stop_loss_pct': trade_params['stop_loss_pct'],
            'take_profit_pct': trade_params['take_profit_pct'],
            'reasoning': strategic_reasoning,
            'order_id': order_id,
            'created_at': entry_time,
            'trading_mode': trading_mode,
            'entry_order_status': entry_order_status
        })
        await self.db.commit()

        position_id = result.scalar()
        return position_id

    async def _set_stop_loss_take_profit(
        self,
        position_id: int,
        pair: str,
        signal: str,
        entry_price: float,
        quantity: float,
        stop_loss_pct: float,
        take_profit_pct: float
    ) -> Dict:
        """
        Set stop loss and take profit.

        STRATEGY (FIXED):
        - TP: Limit order on exchange (passive profit-taking)
        - SL: Software monitoring ONLY (active risk protection via monitor_positions)

        For spot trading, we CANNOT place both TP and SL as limit orders because:
        1. Both would try to lock the same BTC
        2. Only one can succeed (the other fails with insufficient balance)
        3. If TP locks the BTC, SL has no protection

        SOLUTION:
        - Place TP as limit order on exchange
        - Store SL price in database for software monitoring
        - monitor_positions() will trigger market close when price hits SL

        Returns:
            Dict with tp_order_id and sl_order_id (sl_order_id will be None for spot)
        """
        # Calculate SL/TP prices
        if signal == 'BUY':
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100.0)
            take_profit_price = entry_price * (1 + take_profit_pct / 100.0)
            exit_side = "SELL"  # Close BUY with SELL
        else:  # SELL
            stop_loss_price = entry_price * (1 + stop_loss_pct / 100.0)
            take_profit_price = entry_price * (1 - take_profit_pct / 100.0)
            exit_side = "BUY"  # Close SELL with BUY

        # Round prices to reasonable precision
        stop_loss_price = round(stop_loss_price)
        take_profit_price = round(take_profit_price)

        tp_order_id = None
        sl_order_id = None

        # Place TP limit order on exchange (locks the position)
        if self.trading_client:
            try:
                logger.info(f"Placing TP limit {exit_side}: {quantity:.8f} @ R{take_profit_price:,}")
                tp_result = await self.trading_client.place_limit_order(
                    pair=pair,
                    side=exit_side,
                    quantity=quantity,
                    price=take_profit_price
                )

                if tp_result.get('success'):
                    tp_order_id = tp_result.get('orderId') or tp_result.get('id')
                    logger.info(f"TP order placed on exchange: {tp_order_id}")
                else:
                    logger.error(f"TP order failed: {tp_result.get('error')}")
                    # This is CRITICAL - if TP fails, we have no exit order
                    # Position will rely entirely on software monitoring

            except Exception as e:
                logger.error(f"Could not place TP order: {e}")

            # DO NOT place SL as limit order for spot trading
            # SL protection is handled by software monitoring in monitor_positions()
            logger.info(f"SL will be monitored by software @ R{stop_loss_price:,} (no exchange order for spot)")
            sl_order_id = None  # Explicitly None - software monitoring only

        else:
            # Paper mode - simulate order IDs
            tp_order_id = f"PAPER_TP_{datetime.utcnow().timestamp()}"
            sl_order_id = None  # Software monitoring only
            logger.info(f"PAPER: Simulated TP order at R{take_profit_price:,}, SL monitored at R{stop_loss_price:,}")

        # Update database with SL/TP prices and order IDs
        query = text("""
            UPDATE positions
            SET stop_loss_price = :stop_loss,
                take_profit_price = :take_profit,
                tp_order_id = :tp_order_id,
                sl_order_id = :sl_order_id
            WHERE id = :position_id
        """)

        await self.db.execute(query, {
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'tp_order_id': tp_order_id,
            'sl_order_id': sl_order_id,
            'position_id': position_id
        })
        await self.db.commit()

        logger.debug(f"Set SL/TP for position {position_id}: SL={stop_loss_price:,.2f}, TP={take_profit_price:,.2f}")

        return {
            'tp_order_id': tp_order_id,
            'sl_order_id': sl_order_id,
            'tp_price': take_profit_price,
            'sl_price': stop_loss_price
        }

    async def _get_current_price(self, pair: str, price_cache_getter=None) -> float:
        """
        Get current market price with real-time cache and fallback.

        Tries multiple sources in order:
        1. Real-time price cache from WebSocket (sub-second fresh, preferred)
        2. 1m candles (updates every minute)
        3. 5m candles (fallback if 1m not available)
        4. market_trades table (last resort)

        Only uses candle data if less than 10 minutes old to avoid stale prices.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            price_cache_getter: Optional callable to get cached real-time price

        Returns:
            Current price, or 0.0 if no data available
        """
        from datetime import datetime, timedelta

        # Try real-time cache first (WebSocket prices, sub-second fresh)
        if price_cache_getter:
            try:
                cached_price = price_cache_getter(pair)
                if cached_price is not None:
                    logger.debug(f"Got price for {pair} from real-time cache: {cached_price:,.2f}")
                    return cached_price
            except Exception as e:
                logger.warning(f"Error getting cached price for {pair}: {e}")

        # Try 1m candles (freshest data), then fall back to 5m
        for timeframe in ['1m', '5m']:
            query = text("""
                SELECT close_price, close_time
                FROM market_ohlc
                WHERE pair = :pair AND timeframe = :timeframe
                ORDER BY close_time DESC
                LIMIT 1
            """)

            result = await self.db.execute(query, {'pair': pair, 'timeframe': timeframe})
            row = result.fetchone()

            if row:
                close_price = float(row[0])
                close_time = row[1]

                # Check if data is fresh (less than 10 minutes old)
                age = datetime.utcnow() - close_time
                if age < timedelta(minutes=10):
                    logger.debug(f"Got price for {pair} from {timeframe} candle: {close_price:,.2f} (age: {age.total_seconds():.0f}s)")
                    return close_price
                else:
                    logger.warning(f"Skipping stale {timeframe} candle for {pair} (age: {age.total_seconds()/60:.1f} mins)")

        # Fallback to trades table
        query = text("""
            SELECT price
            FROM market_trades
            WHERE pair = :pair
            ORDER BY created_at DESC
            LIMIT 1
        """)

        result = await self.db.execute(query, {'pair': pair})
        row = result.fetchone()

        if row:
            logger.debug(f"Got price for {pair} from trades table: {float(row[0]):,.2f}")
            return float(row[0])

        logger.warning(f"No price data available for {pair}")
        return 0.0

    async def _update_portfolio_value(self, pnl_zar: float):
        """Update portfolio value after closing position."""
        query = text("""
            UPDATE portfolio_state
            SET total_value_zar = total_value_zar + :pnl,
                peak_value_zar = GREATEST(peak_value_zar, total_value_zar + :pnl),
                current_drawdown_pct = CASE
                    WHEN peak_value_zar > 0 THEN
                        (peak_value_zar - (total_value_zar + :pnl)) / peak_value_zar
                    ELSE 0
                END,
                max_drawdown_pct = GREATEST(
                    max_drawdown_pct,
                    CASE
                        WHEN peak_value_zar > 0 THEN
                            (peak_value_zar - (total_value_zar + :pnl)) / peak_value_zar
                        ELSE 0
                    END
                ),
                last_updated = NOW()
            WHERE id = 1
        """)

        await self.db.execute(query, {'pnl': pnl_zar})
        await self.db.commit()

        logger.debug(f"Portfolio value updated: P&L = R{pnl_zar:,.2f}")

    async def _wait_for_fill(
        self,
        order_id: str,
        pair: str,
        timeout_seconds: int = 60
    ) -> Dict:
        """
        Wait for order to fill with timeout and partial fill detection.

        Polls order status every 3 seconds until:
        - Order fills completely (FILLED)
        - Order partially fills and timeout reached (PARTIAL)
        - Timeout reached with no fills (TIMEOUT)

        Args:
            order_id: Order ID to monitor
            pair: Trading pair
            timeout_seconds: Maximum time to wait

        Returns:
            Dict with status, filled_quantity, fill_price
            status: "FILLED", "PARTIAL", "TIMEOUT", "CANCELLED"
        """
        config = get_spot_trading_config()
        elapsed = 0
        last_status = None

        logger.info(f"Waiting for order {order_id[:12]}... to fill (timeout: {timeout_seconds}s)")

        while elapsed < timeout_seconds:
            await asyncio.sleep(config.order_check_interval_seconds)
            elapsed += config.order_check_interval_seconds

            try:
                # Get order status from order history
                order_status = await self._get_order_status(order_id, pair)

                if not order_status:
                    logger.debug(f"[{elapsed}s] Order not found in history yet...")
                    continue

                last_status = order_status
                status = order_status.get('status')
                filled_qty = float(order_status.get('filled_quantity', 0))
                fill_price = float(order_status.get('fill_price', 0))

                logger.debug(f"[{elapsed}s] Order status: {status}, filled: {filled_qty:.8f}")

                if status == 'FILLED' or status == 'Filled':
                    logger.info(f"Order filled: {filled_qty:.8f} @ R{fill_price:,.2f}")
                    return {
                        'status': 'FILLED',
                        'filled_quantity': filled_qty,
                        'fill_price': fill_price
                    }

                elif status == 'CANCELLED' or status == 'Cancelled':
                    logger.warning("Order was cancelled")
                    return {
                        'status': 'CANCELLED',
                        'filled_quantity': 0,
                        'fill_price': 0
                    }

            except Exception as e:
                logger.warning(f"Error checking order status: {e}")
                continue

        # Timeout reached
        if last_status:
            filled_qty = float(last_status.get('filled_quantity', 0))
            if filled_qty > 0:
                # Partial fill detected
                fill_price = float(last_status.get('fill_price', 0))
                logger.warning(f"Timeout with partial fill: {filled_qty:.8f} @ R{fill_price:,.2f}")
                return {
                    'status': 'PARTIAL',
                    'filled_quantity': filled_qty,
                    'fill_price': fill_price
                }

        logger.warning(f"Order timeout after {timeout_seconds}s with no fills")
        return {
            'status': 'TIMEOUT',
            'filled_quantity': 0,
            'fill_price': 0
        }

    async def _get_order_status(self, order_id: str, pair: str) -> Optional[Dict]:
        """
        Get order status from trading client.

        Checks order history to find the order status.

        Returns:
            Dict with status, filled_quantity, fill_price, or None if not found
        """
        if not self.trading_client:
            return None

        try:
            # Get recent order history
            history = await self.trading_client.get_order_history(limit=50)

            # Find our order
            for order in history:
                if order.get('orderId') == order_id or order.get('id') == order_id:
                    return {
                        'status': order.get('orderStatusType') or order.get('status'),
                        'filled_quantity': float(order.get('originalQuantity', 0)),
                        'fill_price': float(order.get('originalPrice', 0))
                    }

            return None

        except Exception as e:
            logger.warning(f"Could not fetch order status: {e}")
            return None
