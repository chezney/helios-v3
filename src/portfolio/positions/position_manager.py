"""
src/portfolio/positions/position_manager.py

Position lifecycle management.

Helios V3.0 - Tier 5: Guardian Portfolio Manager
Phase 5, Week 23: Position Lifecycle Manager
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from enum import Enum
import logging

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
        strategic_reasoning: str
    ) -> Dict:
        """
        Open a new position.

        Steps:
        1. Execute market order via VALR
        2. Record position in database
        3. Set stop loss and take profit levels
        4. Return position details

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: 'BUY' or 'SELL'
            trade_params: Dict with position_size_zar, leverage, stop_loss_pct, take_profit_pct
            strategic_reasoning: LLM reasoning for this trade

        Returns:
            Dict with success, position_id, entry_price, etc.
        """
        logger.info(f"Opening {signal} position for {pair} with size R{trade_params['position_size_zar']:,.2f}")

        # Step 1: Execute market order via VALR
        order_side = 'BUY' if signal == 'BUY' else 'SELL'

        # Get current price
        current_price = await self._get_current_price(pair)
        if current_price == 0.0:
            logger.error(f"Cannot get current price for {pair}")
            return {
                'success': False,
                'error': f'Cannot get current price for {pair}'
            }

        # Calculate quantity
        quantity = trade_params['position_size_zar'] / current_price

        # Execute market order (if trading client available)
        if self.trading_client:
            try:
                order_result = await self.trading_client.place_market_order(
                    pair=pair,
                    side=order_side,
                    quantity=quantity
                )

                if not order_result.get('success'):
                    logger.error(f"Order execution failed: {order_result.get('error')}")
                    return {
                        'success': False,
                        'error': order_result.get('error')
                    }

                entry_price = order_result['fill_price']
                order_id = order_result['order_id']

            except Exception as e:
                logger.error(f"Order execution error: {e}")
                return {
                    'success': False,
                    'error': str(e)
                }
        else:
            # Paper trading mode - simulate order
            logger.info(f"Paper trading mode: simulating {order_side} order")
            entry_price = current_price
            order_id = f"PAPER_{datetime.utcnow().timestamp()}"

        entry_time = datetime.utcnow()

        # Step 2: Record position in database
        position_id = await self._create_position_record(
            pair=pair,
            signal=signal,
            entry_price=entry_price,
            entry_time=entry_time,
            quantity=quantity,
            trade_params=trade_params,
            strategic_reasoning=strategic_reasoning,
            order_id=order_id
        )

        # Step 3: Set stop loss and take profit
        await self._set_stop_loss_take_profit(
            position_id=position_id,
            pair=pair,
            signal=signal,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_pct=trade_params['stop_loss_pct'],
            take_profit_pct=trade_params['take_profit_pct']
        )

        logger.info(f"Position opened successfully: ID={position_id}, entry_price={entry_price:,.2f}")

        return {
            'success': True,
            'position_id': position_id,
            'pair': pair,
            'signal': signal,
            'entry_price': entry_price,
            'quantity': quantity,
            'order_id': order_id
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
            SELECT pair, signal, quantity, entry_price, leverage
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

        # Get current price if not provided
        if current_price is None:
            current_price = await self._get_current_price(pair)

        # Execute closing order (opposite side)
        close_side = 'SELL' if signal == 'BUY' else 'BUY'

        if self.trading_client:
            try:
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
        order_id: str
    ) -> int:
        """Create position record in database."""
        query = text("""
            INSERT INTO positions (
                pair, signal, entry_price, entry_time, quantity,
                position_value_zar, leverage,
                stop_loss_pct, take_profit_pct,
                strategic_reasoning, order_id,
                status, created_at
            ) VALUES (
                :pair, :signal, :entry_price, :entry_time, :quantity,
                :position_value, :leverage,
                :stop_loss_pct, :take_profit_pct,
                :reasoning, :order_id,
                'OPEN', :created_at
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
            'created_at': entry_time
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
    ):
        """Set stop loss and take profit prices."""
        if signal == 'BUY':
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100.0)
            take_profit_price = entry_price * (1 + take_profit_pct / 100.0)
        else:  # SELL
            stop_loss_price = entry_price * (1 + stop_loss_pct / 100.0)
            take_profit_price = entry_price * (1 - take_profit_pct / 100.0)

        query = text("""
            UPDATE positions
            SET stop_loss_price = :stop_loss,
                take_profit_price = :take_profit
            WHERE id = :position_id
        """)

        await self.db.execute(query, {
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'position_id': position_id
        })
        await self.db.commit()

        logger.debug(f"Set SL/TP for position {position_id}: SL={stop_loss_price:,.2f}, TP={take_profit_price:,.2f}")

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
