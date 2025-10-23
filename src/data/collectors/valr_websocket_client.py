"""
Helios Trading System V3.0 - Tier 1: VALR WebSocket Client
Real-Time Price Feed for Position Monitoring and GUI Updates

IMPORTANT: This WebSocket client is SUPPLEMENTARY, not the primary data source.
- Primary data: VALRCandlePoller (REST API polling for 1m candles)
- WebSocket role: Real-time prices for position monitoring, GUI updates, orderbook

VALR WebSocket Limitations:
- NEW_TRADE events are ACCOUNT-ONLY (your executed orders), NOT public market data
- No public trade-by-trade WebSocket available from VALR
- MARKET_SUMMARY_UPDATE provides real-time price snapshots (~1-5 per second)
- AGGREGATED_ORDERBOOK_UPDATE provides orderbook depth (for features)

Architecture Decision:
We use REST API /buckets endpoint for reliable 1m candles (primary data source),
and WebSocket for real-time price updates (supplementary for sub-minute monitoring).
"""

import asyncio
import json
import websockets
import hmac
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
import traceback

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="tier1_data")


@dataclass
class MarketTick:
    """Market tick data structure"""
    pair: str
    price: float
    quantity: float
    side: str  # BUY or SELL
    timestamp: datetime


@dataclass
class OrderBookSnapshot:
    """Order book snapshot structure"""
    pair: str
    bids: List[Dict[str, float]]  # [{"price": float, "quantity": float}, ...]
    asks: List[Dict[str, float]]
    timestamp: datetime


class VALRWebSocketClient:
    """
    WebSocket client for real-time VALR price updates (SUPPLEMENTARY DATA SOURCE).

    Purpose:
    - Real-time price monitoring for position management (stop-loss, take-profit triggers)
    - Sub-second price updates for GUI display
    - Orderbook depth for microstructure features

    NOT used for:
    - Primary candle generation (handled by VALRCandlePoller via REST API)
    - Trade-by-trade data (NEW_TRADE is account-only, not public data)

    Features:
    - MARKET_SUMMARY_UPDATE: Real-time prices (~1-5 per second)
    - AGGREGATED_ORDERBOOK_UPDATE: Bid/ask depth for features
    - Auto-reconnect on disconnection
    - Price update callbacks for position monitoring cache
    """

    def __init__(
        self,
        pairs: List[str] = None,
        on_trade: Optional[Callable[[MarketTick], None]] = None,
        on_orderbook: Optional[Callable[[OrderBookSnapshot], None]] = None,
        on_aggregated_orderbook: Optional[Callable[[Dict], None]] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize WebSocket client with authentication.

        Args:
            pairs: Trading pairs to subscribe to (e.g., ["BTCZAR", "ETHZAR"])
            on_trade: Callback for trade messages
            on_orderbook: Callback for full orderbook snapshots
            on_aggregated_orderbook: Callback for aggregated orderbook updates
            api_key: VALR API key (required for NEW_TRADE events)
            api_secret: VALR API secret (required for NEW_TRADE events)
        """
        self.pairs = pairs or settings.trading.trading_pairs
        self.websocket_url = settings.trading.valr_websocket_url

        # API credentials for authentication
        self.api_key = api_key or settings.trading.valr_api_key
        self.api_secret = api_secret or settings.trading.valr_api_secret

        # Callbacks
        self.on_trade = on_trade
        self.on_orderbook = on_orderbook
        self.on_aggregated_orderbook = on_aggregated_orderbook

        # Connection state
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.running = False

        # Statistics
        self.messages_received = 0
        self.reconnect_count = 0
        self.last_message_time: Optional[datetime] = None

        logger.info(f"VALR WebSocket Client initialized for pairs: {self.pairs} (authenticated={bool(self.api_key)})")

    def _sign_request(self, timestamp: int, verb: str, path: str) -> str:
        """
        Generate HMAC SHA512 signature for WebSocket authentication.

        Args:
            timestamp: Unix timestamp in milliseconds
            verb: HTTP verb (GET for WebSocket)
            path: WebSocket path (/ws/trade or /ws/account)

        Returns:
            Hex-encoded signature
        """
        payload = f"{timestamp}{verb.upper()}{path}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        return signature

    async def connect(self):
        """Connect to VALR WebSocket with authentication"""
        try:
            logger.info(f"Connecting to VALR WebSocket: {self.websocket_url}")

            # Generate authentication headers if API credentials are provided
            extra_headers = {}
            if self.api_key and self.api_secret:
                timestamp = int(time.time() * 1000)
                # Extract path from websocket_url for signature
                from urllib.parse import urlparse
                parsed_url = urlparse(self.websocket_url)
                path = parsed_url.path  # e.g., /ws/account or /ws/trade
                signature = self._sign_request(timestamp, 'GET', path)

                extra_headers = {
                    'X-VALR-API-KEY': self.api_key,
                    'X-VALR-SIGNATURE': signature,
                    'X-VALR-TIMESTAMP': str(timestamp)
                }
                logger.info("WebSocket authentication headers generated")

            self.ws = await websockets.connect(
                self.websocket_url,
                ping_interval=20,
                ping_timeout=10,
                additional_headers=extra_headers if extra_headers else None
            )

            self.connected = True
            logger.info("WebSocket connection established (authenticated)" if extra_headers else "WebSocket connection established (unauthenticated)")

            # Subscribe to data streams
            await self._subscribe()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}", exc_info=True)
            self.connected = False
            return False

    async def _subscribe(self):
        """
        Subscribe to market data streams.

        NOTE: We do NOT subscribe to NEW_TRADE events because they are
        account-only (trades YOU execute), not public market data.

        Subscriptions:
        - AGGREGATED_ORDERBOOK_UPDATE: For bid/ask spread features
        - MARKET_SUMMARY_UPDATE: Handled automatically by VALR (no explicit subscription needed)
        """
        subscriptions = []

        for pair in self.pairs:
            # Subscribe to aggregated orderbook for market microstructure features
            subscriptions.append({
                "type": "SUBSCRIBE",
                "subscriptions": [
                    {"event": "AGGREGATED_ORDERBOOK_UPDATE", "pairs": [pair]}
                ]
            })

        # Send all subscriptions
        for sub in subscriptions:
            await self.ws.send(json.dumps(sub))
            logger.info(f"Subscribed: {sub['subscriptions'][0]['event']} for {sub['subscriptions'][0]['pairs']}")

    async def start(self):
        """Start receiving messages"""
        if not self.connected:
            await self.connect()

        self.running = True
        logger.info("WebSocket client started")

        try:
            while self.running:
                try:
                    # Receive message
                    message = await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=30.0  # 30 second timeout
                    )

                    # Process message
                    await self._process_message(message)

                    # Update stats
                    self.messages_received += 1
                    self.last_message_time = datetime.now(timezone.utc)

                except asyncio.TimeoutError:
                    # No message received in 30 seconds - check connection
                    logger.warning("No message received in 30 seconds, checking connection...")

                    try:
                        # Send ping to check if alive
                        pong = await self.ws.ping()
                        await asyncio.wait_for(pong, timeout=10)
                        logger.info("Connection alive (pong received)")
                    except Exception as e:
                        logger.error(f"Connection dead, reconnecting: {e}")
                        await self._reconnect()

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed, reconnecting...")
                    await self._reconnect()

                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"WebSocket client error: {e}", exc_info=True)
        finally:
            self.running = False
            if self.ws:
                await self.ws.close()
                self.connected = False
            logger.info("WebSocket client stopped")

    async def _reconnect(self):
        """Reconnect to WebSocket"""
        self.reconnect_count += 1
        logger.info(f"Reconnecting... (attempt {self.reconnect_count})")

        try:
            if self.ws:
                await self.ws.close()

            # Wait before reconnecting
            await asyncio.sleep(5)

            # Reconnect
            await self.connect()

            logger.info("Reconnection successful")

        except Exception as e:
            logger.error(f"Reconnection failed: {e}", exc_info=True)
            await asyncio.sleep(10)  # Wait longer on failure

    async def _process_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Get message type
            msg_type = data.get("type")

            if msg_type == "MARKET_SUMMARY_UPDATE":
                await self._handle_market_summary(data)

            elif msg_type == "AGGREGATED_ORDERBOOK_UPDATE":
                await self._handle_aggregated_orderbook(data)

            elif msg_type == "AUTHENTICATED":
                logger.info("WebSocket authenticated")

            elif msg_type is None:
                # Sometimes VALR sends messages without type
                if "data" in data:
                    logger.debug(f"Received data message: {data}")

            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON message: {message}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def _handle_market_summary(self, data: Dict):
        """
        Handle market summary update - Real-time price feed for position monitoring.

        This provides sub-second price updates (~1-5 per second) used by:
        - PositionManager for stop-loss/take-profit triggers
        - GUI for live price display
        - Price monitoring cache

        NOTE: This is NOT used for candle generation (handled by VALRCandlePoller).
        """
        try:
            summary = data.get("data", {})

            pair = summary.get("currencyPairSymbol")
            last_price = float(summary.get("lastTradedPrice", 0))
            base_volume = float(summary.get("baseVolume", 0))
            change_from_previous = float(summary.get("changeFromPrevious", 0))

            logger.debug(
                f"Price Update: {pair} - "
                f"Price: R{last_price:,.2f}, "
                f"24h Volume: {base_volume:,.2f}, "
                f"Change: {change_from_previous:+.2f}%"
            )

            # Call price update callback if exists (for position monitoring cache)
            if self.on_trade and last_price > 0:
                # Reusing on_trade callback for price updates
                # (keeping backward compatibility with existing code)
                tick = MarketTick(
                    pair=pair,
                    price=last_price,
                    quantity=0.0,  # Not relevant for price updates
                    side="PRICE_UPDATE",  # Distinguish from actual trades
                    timestamp=datetime.now(timezone.utc)
                )
                await asyncio.create_task(self.on_trade(tick))

        except Exception as e:
            logger.error(f"Error handling market summary: {e}", exc_info=True)

    async def _handle_aggregated_orderbook(self, data: Dict):
        """Handle aggregated orderbook update"""
        try:
            pair = data.get("currencyPairSymbol")
            orderbook_data = data.get("data", {})

            bids = orderbook_data.get("Bids", [])
            asks = orderbook_data.get("Asks", [])

            # Convert to our format
            bids_formatted = [
                {"price": float(b["price"]), "quantity": float(b["quantity"])}
                for b in bids[:10]  # Top 10 levels
            ]

            asks_formatted = [
                {"price": float(a["price"]), "quantity": float(a["quantity"])}
                for a in asks[:10]  # Top 10 levels
            ]

            logger.debug(
                f"Order Book: {pair} - "
                f"Best Bid: R{bids_formatted[0]['price']:,.2f}, "
                f"Best Ask: R{asks_formatted[0]['price']:,.2f}"
                if bids_formatted and asks_formatted else
                f"Order Book: {pair} (empty)"
            )

            # Call orderbook callback if exists
            if self.on_orderbook:
                snapshot = OrderBookSnapshot(
                    pair=pair,
                    bids=bids_formatted,
                    asks=asks_formatted,
                    timestamp=datetime.now(timezone.utc)
                )
                await asyncio.create_task(self.on_orderbook(snapshot))

            # Call aggregated orderbook callback if exists
            if self.on_aggregated_orderbook:
                await asyncio.create_task(self.on_aggregated_orderbook(data))

        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)


    async def stop(self):
        """Stop the WebSocket client"""
        logger.info("Stopping WebSocket client...")
        self.running = False

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")

        self.connected = False
        logger.info("WebSocket client stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            "connected": self.connected,
            "running": self.running,
            "messages_received": self.messages_received,
            "reconnect_count": self.reconnect_count,
            "last_message_time": (
                self.last_message_time.isoformat()
                if self.last_message_time
                else None
            ),
            "pairs": self.pairs
        }


# Example usage and testing
if __name__ == "__main__":
    async def handle_trade(tick: MarketTick):
        """Example trade handler"""
        print(f"[TRADE] {tick.pair}: {tick.side} {tick.quantity:,.8f} @ R{tick.price:,.2f}")

    async def handle_orderbook(snapshot: OrderBookSnapshot):
        """Example orderbook handler"""
        if snapshot.bids and snapshot.asks:
            best_bid = snapshot.bids[0]['price']
            best_ask = snapshot.asks[0]['price']
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid) * 100

            print(
                f"[ORDERBOOK] {snapshot.pair}: "
                f"Bid R{best_bid:,.2f} / Ask R{best_ask:,.2f} "
                f"(Spread: R{spread:,.2f}, {spread_pct:.3f}%)"
            )

    async def main():
        """Test WebSocket client"""
        print("\n" + "=" * 60)
        print("  VALR WebSocket Client Test")
        print("=" * 60 + "\n")

        client = VALRWebSocketClient(
            pairs=["BTCZAR"],
            on_trade=handle_trade,
            on_orderbook=handle_orderbook
        )

        try:
            # Start client
            await client.start()

        except KeyboardInterrupt:
            print("\n\nStopping...")
            await client.stop()

        # Print stats
        stats = client.get_stats()
        print("\n" + "=" * 60)
        print("  Statistics")
        print("=" * 60)
        print(f"  Messages Received: {stats['messages_received']}")
        print(f"  Reconnect Count: {stats['reconnect_count']}")
        print(f"  Last Message: {stats['last_message_time']}")
        print("=" * 60 + "\n")

    asyncio.run(main())
