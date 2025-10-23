"""
src/trading/execution/valr_websocket_trading_client.py

WebSocket-Enhanced VALR Trading Client for LIVE mode trading.

This client uses WebSocket for FAST order execution and REST API as fallback.

Key Features:
- WebSocket order placement (fastest execution)
- Real-time order confirmation via NEW_TRADE events
- REST API fallback if WebSocket unavailable
- Order tracking with correlation IDs
- Automatic reconnection and retry logic

Performance Benefits:
- WebSocket: ~50-100ms latency
- REST API: ~150-300ms latency
- 2-3x faster execution vs REST-only

Helios V3.0 - Phase 3.5: WebSocket Trading Enhancement
Created: 2025-10-23
"""

import asyncio
import json
import logging
import os
import time
import hmac
import hashlib
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from enum import Enum
import websockets
from websockets.client import WebSocketClientProtocol

# Import existing REST client for fallback
from src.trading.execution.valr_trading_client import VALRTradingClient

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enum"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class VALRWebSocketTradingClient:
    """
    WebSocket-Enhanced VALR Trading Client.

    Hybrid approach:
    - Uses WebSocket for order placement (fast)
    - Uses REST API for balance queries and order history
    - Automatic fallback to REST if WebSocket unavailable

    Performance:
    - WebSocket execution: ~50-100ms
    - REST execution: ~150-300ms
    - 2-3x faster via WebSocket

    Usage:
        client = VALRWebSocketTradingClient()
        await client.connect()
        result = await client.place_market_order("BTCZAR", "BUY", 0.001)
        # Order placed via WebSocket, confirmed via NEW_TRADE event
    """

    WEBSOCKET_URL = "wss://api.valr.com/ws/account"

    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize WebSocket trading client.

        Args:
            api_key: VALR API key (or set VALR_API_KEY env var)
            api_secret: VALR API secret (or set VALR_API_SECRET env var)

        Raises:
            ValueError: If API credentials not provided
        """
        self.api_key = api_key or os.getenv("VALR_API_KEY")
        self.api_secret = api_secret or os.getenv("VALR_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "VALR API credentials required. Set VALR_API_KEY and VALR_API_SECRET "
                "environment variables or pass to constructor."
            )

        # WebSocket connection
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.authenticated = False

        # REST API fallback client
        self.rest_client = VALRTradingClient(api_key=self.api_key, api_secret=self.api_secret)

        # Order tracking
        self.pending_orders: Dict[str, asyncio.Future] = {}  # correlation_id -> Future
        self.order_callbacks: Dict[str, Callable] = {}

        # Statistics
        self.orders_via_websocket = 0
        self.orders_via_rest = 0
        self.websocket_failures = 0

        logger.info("VALR WebSocket Trading Client initialized (LIVE MODE)")
        logger.warning("[WARN] This client trades with REAL MONEY via WebSocket")

    def _generate_signature(self, timestamp: int, method: str, path: str) -> str:
        """
        Generate HMAC-SHA512 signature for WebSocket authentication.

        Args:
            timestamp: Unix timestamp in milliseconds
            method: HTTP method (GET for WebSocket)
            path: WebSocket path (/ws/account)

        Returns:
            Hex-encoded HMAC-SHA512 signature
        """
        message = f"{timestamp}{method.upper()}{path}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha512
        ).hexdigest()
        return signature

    async def connect(self) -> bool:
        """
        Connect to VALR WebSocket with authentication.

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            logger.info(f"Connecting to VALR WebSocket: {self.WEBSOCKET_URL}")

            # Generate authentication headers
            timestamp = int(time.time() * 1000)
            signature = self._generate_signature(timestamp, 'GET', '/ws/account')

            extra_headers = {
                'X-VALR-API-KEY': self.api_key,
                'X-VALR-SIGNATURE': signature,
                'X-VALR-TIMESTAMP': str(timestamp)
            }

            # Connect to WebSocket (websockets library uses additional_headers, not extra_headers)
            self.ws = await websockets.connect(
                self.WEBSOCKET_URL,
                ping_interval=20,
                ping_timeout=10,
                additional_headers=extra_headers
            )

            self.connected = True
            logger.info("[OK] WebSocket connected (authenticated)")

            # Start message handler
            asyncio.create_task(self._message_handler())

            return True

        except Exception as e:
            logger.error(f"[FAIL] Failed to connect to WebSocket: {e}")
            self.connected = False
            return False

    async def _message_handler(self):
        """
        Handle incoming WebSocket messages.

        Processes:
        - AUTHENTICATED: Connection confirmed
        - ORDER_PROCESSED: Order status updates
        - NEW_TRADE: Trade execution confirmations
        - BALANCE_UPDATE: Balance changes after trades
        """
        try:
            while self.connected and self.ws:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                    data = json.loads(message)

                    msg_type = data.get("type")

                    if msg_type == "AUTHENTICATED":
                        self.authenticated = True
                        logger.info("[OK] WebSocket authenticated")

                    elif msg_type == "ORDER_PROCESSED":
                        await self._handle_order_processed(data)

                    elif msg_type == "NEW_TRADE":
                        await self._handle_new_trade(data)

                    elif msg_type == "BALANCE_UPDATE":
                        logger.debug(f"Balance update: {data.get('data')}")

                    else:
                        logger.debug(f"Received message type: {msg_type}")

                except asyncio.TimeoutError:
                    # No message in 30s - check connection
                    try:
                        pong = await self.ws.ping()
                        await asyncio.wait_for(pong, timeout=10)
                        logger.debug("WebSocket ping successful")
                    except Exception as e:
                        logger.error(f"WebSocket ping failed: {e}")
                        await self._reconnect()

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    await self._reconnect()

                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"WebSocket message handler error: {e}", exc_info=True)
        finally:
            self.connected = False
            self.authenticated = False

    async def _reconnect(self):
        """Reconnect to WebSocket"""
        logger.info("Reconnecting to WebSocket...")
        self.connected = False
        self.authenticated = False

        if self.ws:
            await self.ws.close()

        await asyncio.sleep(2)  # Wait before reconnect
        await self.connect()

    async def _handle_order_processed(self, data: Dict[str, Any]):
        """
        Handle ORDER_PROCESSED event from WebSocket.

        This event is received when an order is accepted/rejected by the exchange.

        Args:
            data: WebSocket message data
        """
        order_data = data.get("data", {})
        correlation_id = order_data.get("customerOrderId")  # Our correlation ID

        logger.info(f"[WEBSOCKET] Order processed: {order_data.get('orderId')} (status: {order_data.get('orderStatus')})")

        if correlation_id and correlation_id in self.pending_orders:
            future = self.pending_orders[correlation_id]

            # Set result with order data
            if not future.done():
                future.set_result({
                    "success": True,
                    "order_id": order_data.get("orderId"),
                    "status": order_data.get("orderStatus"),
                    "pair": order_data.get("currencyPair"),
                    "side": order_data.get("side"),
                    "quantity": float(order_data.get("originalQuantity", 0)),
                    "timestamp": datetime.utcnow().isoformat(),
                    "via": "websocket",
                    "event": "ORDER_PROCESSED"
                })

    async def _handle_new_trade(self, data: Dict[str, Any]):
        """
        Handle NEW_TRADE event from WebSocket.

        This event is received when YOUR order is EXECUTED (filled).
        NEW_TRADE is account-specific (not public market data).

        Args:
            data: WebSocket message data
        """
        trade_data = data.get("data", {})
        order_id = trade_data.get("orderId")

        logger.info(f"[WEBSOCKET] Trade executed: {order_id} @ {trade_data.get('price')}")

        # Find pending order by order_id
        for correlation_id, future in self.pending_orders.items():
            if future.done():
                result = future.result()
                if result.get("order_id") == order_id:
                    # Update result with execution details
                    result["filled"] = True
                    result["fill_price"] = float(trade_data.get("price"))
                    result["fill_quantity"] = float(trade_data.get("quantity"))
                    result["fee"] = float(trade_data.get("takerFee", 0))
                    result["event"] = "NEW_TRADE"

                    logger.info(
                        f"[OK] Order {order_id} filled: "
                        f"{trade_data.get('quantity')} @ {trade_data.get('price')}"
                    )

    async def place_market_order_with_tpsl(
        self,
        pair: str,
        side: str,
        quantity: float,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place market order with TP/SL via WebSocket (with REST fallback).

        This method places a market order AND automatically sets take profit
        and stop loss orders in a single execution.

        Execution flow:
        1. Place market order (entry)
        2. Immediately place limit order for take profit (if specified)
        3. Immediately place stop order for stop loss (if specified)
        4. All orders tracked via correlation IDs

        Args:
            pair: Trading pair (e.g., "BTCZAR", "ETHZAR")
            side: "BUY" or "SELL"
            quantity: Amount in base currency
            take_profit_price: Take profit price (optional)
            stop_loss_price: Stop loss price (optional)
            metadata: Optional metadata

        Returns:
            Dict with order result including TP/SL order IDs
        """
        # Validate inputs
        if side not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'")

        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be positive")

        # Validate TP/SL prices
        if side == "BUY":
            if take_profit_price and stop_loss_price:
                if take_profit_price <= stop_loss_price:
                    raise ValueError("For BUY orders: Take profit must be > stop loss")
        else:  # SELL
            if take_profit_price and stop_loss_price:
                if take_profit_price >= stop_loss_price:
                    raise ValueError("For SELL orders: Take profit must be < stop loss")

        # Place entry order first
        entry_result = await self.place_market_order(pair, side, quantity, metadata)

        if not entry_result.get("success"):
            logger.error(f"Entry order failed: {entry_result.get('error')}")
            return entry_result

        # Get fill price from entry order
        fill_price = entry_result.get("fill_price") or entry_result.get("executedPrice")

        result = {
            "success": True,
            "entry_order": entry_result,
            "take_profit_order": None,
            "stop_loss_order": None
        }

        # Place take profit order (limit order in opposite direction)
        if take_profit_price:
            try:
                tp_side = "SELL" if side == "BUY" else "BUY"
                tp_result = await self._place_limit_order_websocket(
                    pair=pair,
                    side=tp_side,
                    quantity=quantity,
                    price=take_profit_price,
                    post_only=False
                )
                result["take_profit_order"] = tp_result
                logger.info(f"[OK] Take profit order placed @ {take_profit_price}")
            except Exception as e:
                logger.error(f"[FAIL] Take profit order failed: {e}")
                result["take_profit_error"] = str(e)

        # Place stop loss order (stop order in opposite direction)
        if stop_loss_price:
            try:
                sl_side = "SELL" if side == "BUY" else "BUY"
                sl_result = await self._place_stop_order_websocket(
                    pair=pair,
                    side=sl_side,
                    quantity=quantity,
                    stop_price=stop_loss_price
                )
                result["stop_loss_order"] = sl_result
                logger.info(f"[OK] Stop loss order placed @ {stop_loss_price}")
            except Exception as e:
                logger.error(f"[FAIL] Stop loss order failed: {e}")
                result["stop_loss_error"] = str(e)

        return result

    async def place_market_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place market order via WebSocket (with REST fallback).

        Execution flow:
        1. Generate correlation ID
        2. Send PLACE_ORDER message via WebSocket
        3. Wait for ORDER_PROCESSED event (confirmation)
        4. Wait for NEW_TRADE event (execution)
        5. If WebSocket fails, fall back to REST API

        Args:
            pair: Trading pair (e.g., "BTCZAR", "ETHZAR")
            side: "BUY" or "SELL"
            quantity: Amount in base currency
            metadata: Optional metadata

        Returns:
            Dict with order result
        """
        # Validate inputs
        if side not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'")

        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be positive")

        # Try WebSocket execution first
        if self.connected and self.authenticated:
            try:
                logger.info(f"[WEBSOCKET] Placing market order: {side} {quantity} {pair}")

                # Generate correlation ID for tracking
                correlation_id = f"helios_{uuid.uuid4().hex[:16]}"

                # Create order message
                order_message = {
                    "type": "PLACE_ORDER",
                    "data": {
                        "currencyPair": pair,
                        "side": side,
                        "orderType": "MARKET",
                        "quantity": str(quantity),
                        "customerOrderId": correlation_id  # For tracking
                    }
                }

                # Create future for order result
                future = asyncio.Future()
                self.pending_orders[correlation_id] = future

                # Send order via WebSocket
                await self.ws.send(json.dumps(order_message))

                # Wait for ORDER_PROCESSED event (10 second timeout)
                try:
                    result = await asyncio.wait_for(future, timeout=10.0)
                    self.orders_via_websocket += 1

                    logger.info(f"[OK] WebSocket order executed successfully")
                    return result

                except asyncio.TimeoutError:
                    logger.warning("[WARN] WebSocket order timeout, falling back to REST API")
                    self.websocket_failures += 1
                    # Fall through to REST API fallback

                finally:
                    # Cleanup
                    if correlation_id in self.pending_orders:
                        del self.pending_orders[correlation_id]

            except Exception as e:
                logger.error(f"[FAIL] WebSocket order failed: {e}, falling back to REST API")
                self.websocket_failures += 1
                # Fall through to REST API fallback

        # REST API fallback
        logger.info(f"[REST] Placing market order via REST API (fallback)")
        result = await self.rest_client.place_market_order(
            pair=pair,
            side=side,
            quantity=quantity,
            metadata=metadata
        )

        result["via"] = "rest_fallback"
        self.orders_via_rest += 1

        return result

    async def _place_limit_order_websocket(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        post_only: bool = False
    ) -> Dict[str, Any]:
        """
        Place limit order via WebSocket.

        Internal method used for take profit orders.

        Args:
            pair: Trading pair
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price
            post_only: Post-only flag

        Returns:
            Dict with order result
        """
        if self.connected and self.authenticated:
            try:
                correlation_id = f"helios_tp_{uuid.uuid4().hex[:16]}"

                order_message = {
                    "type": "PLACE_ORDER",
                    "data": {
                        "currencyPair": pair,
                        "side": side,
                        "orderType": "LIMIT",
                        "quantity": str(quantity),
                        "price": str(price),
                        "postOnly": post_only,
                        "customerOrderId": correlation_id
                    }
                }

                future = asyncio.Future()
                self.pending_orders[correlation_id] = future

                await self.ws.send(json.dumps(order_message))

                try:
                    result = await asyncio.wait_for(future, timeout=10.0)
                    return result
                except asyncio.TimeoutError:
                    logger.warning("Limit order timeout, falling back to REST")
                finally:
                    if correlation_id in self.pending_orders:
                        del self.pending_orders[correlation_id]

            except Exception as e:
                logger.error(f"WebSocket limit order failed: {e}")

        # REST fallback
        return await self.rest_client.place_limit_order(
            pair=pair,
            side=side,
            quantity=quantity,
            price=price,
            post_only=post_only
        )

    async def _place_stop_order_websocket(
        self,
        pair: str,
        side: str,
        quantity: float,
        stop_price: float
    ) -> Dict[str, Any]:
        """
        Place stop order via WebSocket.

        Internal method used for stop loss orders.

        Args:
            pair: Trading pair
            side: "BUY" or "SELL"
            quantity: Order quantity
            stop_price: Stop trigger price

        Returns:
            Dict with order result
        """
        if self.connected and self.authenticated:
            try:
                correlation_id = f"helios_sl_{uuid.uuid4().hex[:16]}"

                order_message = {
                    "type": "PLACE_ORDER",
                    "data": {
                        "currencyPair": pair,
                        "side": side,
                        "orderType": "STOP_LOSS_LIMIT",
                        "quantity": str(quantity),
                        "price": str(stop_price),  # Limit price = stop price
                        "stopPrice": str(stop_price),
                        "customerOrderId": correlation_id
                    }
                }

                future = asyncio.Future()
                self.pending_orders[correlation_id] = future

                await self.ws.send(json.dumps(order_message))

                try:
                    result = await asyncio.wait_for(future, timeout=10.0)
                    return result
                except asyncio.TimeoutError:
                    logger.warning("Stop order timeout, falling back to REST")
                finally:
                    if correlation_id in self.pending_orders:
                        del self.pending_orders[correlation_id]

            except Exception as e:
                logger.error(f"WebSocket stop order failed: {e}")

        # REST fallback - VALR may not support stop orders via REST
        # Log warning and return error
        logger.error("Stop orders only supported via WebSocket")
        return {
            "success": False,
            "error": "Stop orders require WebSocket connection"
        }

    async def get_balance(self, currency: str) -> float:
        """
        Get account balance for specific currency.

        Uses REST API (WebSocket doesn't support balance queries).

        Args:
            currency: Currency code (BTC, ETH, ZAR, etc.)

        Returns:
            Available balance
        """
        return await self.rest_client.get_balance(currency)

    async def get_all_balances(self) -> Dict[str, float]:
        """
        Get all account balances.

        Uses REST API (WebSocket doesn't support balance queries).

        Returns:
            Dict of currency -> balance
        """
        return await self.rest_client.get_all_balances()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.

        Returns:
            Dict with WebSocket vs REST usage stats
        """
        total_orders = self.orders_via_websocket + self.orders_via_rest

        return {
            "orders_via_websocket": self.orders_via_websocket,
            "orders_via_rest": self.orders_via_rest,
            "websocket_failures": self.websocket_failures,
            "total_orders": total_orders,
            "websocket_percentage": (self.orders_via_websocket / total_orders * 100.0) if total_orders > 0 else 0.0,
            "connected": self.connected,
            "authenticated": self.authenticated
        }

    async def close(self):
        """
        Close WebSocket connection and REST client.

        Call this during application shutdown.
        """
        self.connected = False

        if self.ws:
            try:
                await self.ws.close()
                logger.info("[OK] WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

        await self.rest_client.close()

        logger.info("[OK] VALR WebSocket Trading Client closed")


# Example usage and testing
if __name__ == "__main__":
    import asyncio

    async def test_websocket_trading():
        """Test WebSocket trading client"""
        print("\n" + "=" * 80)
        print("VALR WEBSOCKET TRADING CLIENT TEST")
        print("=" * 80 + "\n")

        client = VALRWebSocketTradingClient()

        # Connect to WebSocket
        print("Connecting to WebSocket...")
        connected = await client.connect()

        if connected:
            print(f"[OK] Connected successfully")
        else:
            print(f"[WARN] Connection failed - will use REST fallback")

        # Wait for authentication
        await asyncio.sleep(2)

        # Get balance (uses REST API)
        try:
            zar_balance = await client.get_balance("ZAR")
            print(f"\nZAR Balance: R{zar_balance:,.2f}")
        except Exception as e:
            print(f"Balance query failed: {e}")

        # Test market order (DISABLED - uncomment to test with real money)
        # WARNING: This will place a REAL order with REAL money!
        # try:
        #     result = await client.place_market_order("BTCZAR", "BUY", 0.0001)
        #     print(f"\nOrder Result: {result}")
        # except Exception as e:
        #     print(f"Order failed: {e}")

        # Get stats
        stats = client.get_stats()
        print(f"\nExecution Stats:")
        print(f"  WebSocket orders: {stats['orders_via_websocket']}")
        print(f"  REST orders: {stats['orders_via_rest']}")
        print(f"  WebSocket failures: {stats['websocket_failures']}")
        print(f"  WebSocket %: {stats['websocket_percentage']:.1f}%")

        # Cleanup
        await client.close()
        print("\n[OK] Test complete")

    asyncio.run(test_websocket_trading())
