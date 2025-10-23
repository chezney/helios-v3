"""
src/data/streaming/live_candle_generator.py

DEPRECATED (October 2025) - DO NOT USE FOR NEW DEVELOPMENT
==========================================================

This module is DEPRECATED and replaced by VALRCandlePoller (REST API polling).

REASON FOR DEPRECATION:
-----------------------
VALR's NEW_TRADE WebSocket events are account-only (trades you execute), NOT
public market data. This was discovered in October 2025 after VALR support confirmed
that no public WebSocket stream for trades exists.

NEW ARCHITECTURE (October 2025):
---------------------------------
1. Primary Data Source: VALRCandlePoller (src/data/collectors/valr_candle_poller.py)
   - Polls VALR REST API /buckets endpoint every 60 seconds
   - Fetches pre-aggregated 1-minute candles directly from VALR
   - More reliable and accurate (official VALR candles)
   - No dependency on trade-by-trade WebSocket feeds

2. Supplementary: VALRWebSocketClient (src/data/collectors/valr_websocket_client.py)
   - MARKET_SUMMARY_UPDATE for real-time prices (~1-5 per second)
   - Used for position monitoring (stop-loss/take-profit triggers)
   - AGGREGATED_ORDERBOOK_UPDATE for bid/ask spread features

MIGRATION GUIDE:
----------------
DO NOT create new instances of LiveCandleGenerator.

Instead, use:
```python
from src.data.collectors.valr_candle_poller import VALRCandlePoller

# Create poller (requires asyncpg database connection)
poller = VALRCandlePoller(
    db=db_connection,  # asyncpg connection
    pairs=["BTCZAR", "ETHZAR", "SOLZAR"],
    event_queue=event_queue  # Same queue for NEW_CANDLE events
)

# Start polling (runs every 60 seconds)
await poller.start()
```

For real-time prices (position monitoring):
```python
from src.data.collectors.valr_websocket_client import VALRWebSocketClient

def on_price_update(tick):
    # Handle real-time price updates
    print(f"{tick.pair}: R{tick.price:,.2f}")

ws_client = VALRWebSocketClient(
    pairs=["BTCZAR", "ETHZAR", "SOLZAR"],
    on_trade=on_price_update  # Callback for MARKET_SUMMARY_UPDATE
)

await ws_client.start()
```

HISTORICAL NOTE:
----------------
This module was created in Phase 6 (Week 27) to generate OHLC candles from
WebSocket trade events. It worked well in testing but relied on NEW_TRADE
events which turned out to be account-only data.

File kept for historical reference only. Will be removed in future cleanup.

Original Description (obsolete):
---------------------------------
Live Candle Generator - Real-time OHLC candle generation from WebSocket.
Bridges VALR WebSocket client to Autonomous Trading Engine event queue.

Helios V3.0 - Phase 6: Week 27 WebSocket Integration (DEPRECATED)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable
from collections import defaultdict
import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.data.collectors.valr_websocket_client import VALRWebSocketClient, MarketTick
from src.data.processors.candle_aggregator import CandleBuilder, OHLC

logger = logging.getLogger(__name__)


class LiveCandleGenerator:
    """
    DEPRECATED - Real-time candle generator from WebSocket trades.

    ⚠️ WARNING: This class is DEPRECATED as of October 2025.
    ⚠️ DO NOT USE for new development.
    ⚠️ Use VALRCandlePoller instead (see module docstring for migration guide).

    DEPRECATION REASON:
    VALR NEW_TRADE WebSocket events are account-only (not public market data).
    This was confirmed by VALR support in October 2025.

    REPLACEMENT:
    - Primary: VALRCandlePoller (REST API /buckets endpoint, 60-second polling)
    - Supplementary: VALRWebSocketClient (real-time prices for position monitoring)

    Original Features (for historical reference):
    - Subscribes to VALR WebSocket for real-time trades
    - Maintains multi-timeframe candle builders (1m, 5m, 15m)
    - Emits NEW_CANDLE events when candles close
    - Emits PRICE_UPDATE events for position monitoring
    - Auto-handles candle period transitions

    Integration (OBSOLETE):
    - Input: VALR WebSocket trades (account-only, not public data!)
    - Output: Events to autonomous engine queue
    """

    def __init__(
        self,
        pairs: List[str],
        event_queue: asyncio.Queue,
        db_session: Optional[AsyncSession] = None,
        timeframes: List[str] = None,
        compute_features: bool = False
    ):
        """
        Initialize live candle generator.

        Args:
            pairs: Trading pairs to track (e.g., ["BTCZAR", "ETHZAR"])
            event_queue: Async queue to push events to
            db_session: Database session for persisting candles (optional)
            timeframes: Timeframes to generate (default: ["1m", "5m", "15m"])
            compute_features: Whether to compute and store 90-feature vectors (requires historical data)
        """
        self.pairs = pairs
        self.event_queue = event_queue
        self.db_session = db_session
        self.timeframes = timeframes or ["1m", "5m", "15m"]
        self.compute_features = compute_features

        # Candle builders: {(pair, timeframe): CandleBuilder}
        self.builders: Dict[tuple, CandleBuilder] = {}

        # Last candle timestamps: {(pair, timeframe): datetime}
        self.last_candle_times: Dict[tuple, datetime] = {}

        # Historical candles for feature computation: {pair: {timeframe: List[OHLC]}}
        self.historical_candles: Dict[str, Dict[str, List[OHLC]]] = defaultdict(lambda: defaultdict(list))

        # Feature engineer (lazy initialization)
        self.feature_engineer = None
        if compute_features:
            try:
                from src.data.processors.feature_engineering import FeatureEngineer
                self.feature_engineer = FeatureEngineer()
                logger.info("Feature engineering enabled (90-feature computation)")
            except ImportError as e:
                logger.warning(f"Feature engineering not available: {e}")
                self.compute_features = False

        # WebSocket client
        self.websocket_client: Optional[VALRWebSocketClient] = None

        # Running state
        self.running = False

        # Statistics
        self.trades_processed = 0
        self.candles_generated = 0
        self.candles_persisted = 0
        self.features_computed = 0

        logger.info(
            f"LiveCandleGenerator initialized: pairs={pairs}, "
            f"timeframes={self.timeframes}, "
            f"db_persistence={'enabled' if db_session else 'disabled'}, "
            f"feature_computation={'enabled' if compute_features else 'disabled'}"
        )

    async def start(self):
        """Start live candle generation."""
        logger.info("Starting live candle generator...")

        # Preload historical candles from database for feature computation
        if self.db_session and self.compute_features:
            await self._preload_historical_candles()

        # Initialize WebSocket client
        self.websocket_client = VALRWebSocketClient(
            pairs=self.pairs,
            on_trade=self._on_trade_callback,
            on_orderbook=self._on_orderbook_callback
        )

        # Initialize candle builders
        self._initialize_builders()

        # Start WebSocket
        try:
            await self.websocket_client.connect()
            self.running = True

            # Start WebSocket message loop in background
            asyncio.create_task(self.websocket_client.start())

            # Start candle finalization loop
            asyncio.create_task(self._candle_finalization_loop())

            logger.info("Live candle generator started successfully")

        except Exception as e:
            logger.error(f"Failed to start candle generator: {e}", exc_info=True)
            raise

    def _initialize_builders(self):
        """Initialize candle builders for all pairs and timeframes."""
        now = self._get_candle_start_time("1m")  # Use 1m for initialization

        for pair in self.pairs:
            for timeframe in self.timeframes:
                key = (pair, timeframe)

                # Get start time for this timeframe
                start_time = self._get_candle_start_time(timeframe)

                # Create builder
                self.builders[key] = CandleBuilder(
                    pair=pair,
                    timeframe=timeframe,
                    start_time=start_time
                )

                # Track candle time
                self.last_candle_times[key] = start_time

                logger.debug(
                    f"Initialized builder: {pair} {timeframe} "
                    f"(start: {start_time.strftime('%H:%M:%S')})"
                )

    def _get_candle_start_time(self, timeframe: str) -> datetime:
        """
        Get the start time for current candle period.

        Args:
            timeframe: "1m", "5m", or "15m"

        Returns:
            Start time of current candle period
        """
        now = datetime.now(timezone.utc)

        # Get timeframe duration in minutes
        minutes = int(timeframe.replace("m", ""))

        # Round down to nearest period start
        current_minute = now.minute
        period_start_minute = (current_minute // minutes) * minutes

        start_time = now.replace(
            minute=period_start_minute,
            second=0,
            microsecond=0
        )

        return start_time

    async def _on_trade_callback(self, tick: MarketTick):
        """
        Handle incoming trade from WebSocket.

        Args:
            tick: Market tick with price, quantity, etc.
        """
        try:
            # Add trade to all timeframe builders for this pair
            for timeframe in self.timeframes:
                key = (tick.pair, timeframe)

                if key in self.builders:
                    # Check if we need to finalize current candle
                    await self._check_candle_period(key)

                    # Add trade to builder
                    self.builders[key].add_trade(tick.price, tick.quantity)

            # Emit price update event for position monitoring
            await self.event_queue.put({
                "type": "PRICE_UPDATE",
                "pair": tick.pair,
                "price": tick.price,
                "timestamp": tick.timestamp.isoformat()
            })

            self.trades_processed += 1

            if self.trades_processed % 100 == 0:
                logger.debug(f"Processed {self.trades_processed} trades")

        except Exception as e:
            logger.error(f"Error processing trade: {e}", exc_info=True)

    async def _on_orderbook_callback(self, snapshot):
        """
        Handle orderbook update from WebSocket.

        Args:
            snapshot: OrderBook snapshot
        """
        try:
            # Emit orderbook event
            await self.event_queue.put({
                "type": "ORDERBOOK_UPDATE",
                "pair": snapshot.pair,
                "best_bid": snapshot.bids[0]['price'] if snapshot.bids else 0,
                "best_ask": snapshot.asks[0]['price'] if snapshot.asks else 0,
                "timestamp": snapshot.timestamp.isoformat()
            })

        except Exception as e:
            logger.error(f"Error processing orderbook: {e}", exc_info=True)

    async def _check_candle_period(self, key: tuple):
        """
        Check if candle period has ended and finalize if needed.

        Args:
            key: (pair, timeframe) tuple
        """
        pair, timeframe = key

        # Get current period start
        current_period_start = self._get_candle_start_time(timeframe)

        # Get last period start
        last_period_start = self.last_candle_times.get(key)

        # If period changed, finalize previous candle
        if last_period_start and current_period_start > last_period_start:
            await self._finalize_candle(key)

    async def _persist_candle_to_database(self, candle: OHLC, pair: str, timeframe: str):
        """
        Persist candle to market_ohlc table.

        Args:
            candle: OHLC candle object
            pair: Trading pair
            timeframe: Timeframe (e.g., "1m", "5m", "15m")
        """
        if not self.db_session:
            return

        try:
            # Calculate close time based on timeframe
            minutes = int(timeframe.replace("m", ""))
            close_time = candle.timestamp + timedelta(minutes=minutes)

            # Convert to naive datetime (remove timezone) for PostgreSQL compatibility
            open_time_naive = candle.timestamp.replace(tzinfo=None) if candle.timestamp.tzinfo else candle.timestamp
            close_time_naive = close_time.replace(tzinfo=None) if close_time.tzinfo else close_time

            # Insert into market_ohlc table
            query = text("""
                INSERT INTO market_ohlc (
                    pair, timeframe,
                    open_price, high_price, low_price, close_price,
                    volume, num_trades,
                    open_time, close_time
                ) VALUES (
                    :pair, :timeframe,
                    :open_price, :high_price, :low_price, :close_price,
                    :volume, :num_trades,
                    :open_time, :close_time
                )
                ON CONFLICT (pair, timeframe, open_time) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    num_trades = EXCLUDED.num_trades,
                    close_time = EXCLUDED.close_time
            """)

            await self.db_session.execute(query, {
                'pair': pair,
                'timeframe': timeframe,
                'open_price': float(candle.open),
                'high_price': float(candle.high),
                'low_price': float(candle.low),
                'close_price': float(candle.close),
                'volume': float(candle.volume),
                'num_trades': candle.trade_count,
                'open_time': open_time_naive,
                'close_time': close_time_naive
            })

            await self.db_session.commit()
            self.candles_persisted += 1

            logger.debug(
                f"Persisted candle to DB: {pair} {timeframe} "
                f"@ {candle.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(f"Failed to persist candle to database: {e}", exc_info=True)
            await self.db_session.rollback()

    async def _preload_historical_candles(self):
        """
        Preload last 100 candles from database for each pair/timeframe.
        This enables immediate feature calculation on startup.
        """
        try:
            from sqlalchemy import text

            for pair in self.pairs:
                for timeframe in self.timeframes:
                    query = text("""
                        SELECT pair, timeframe, open_time, open_price, high_price,
                               low_price, close_price, volume, num_trades
                        FROM market_ohlc
                        WHERE pair = :pair AND timeframe = :timeframe
                        ORDER BY open_time DESC
                        LIMIT 100
                    """)

                    result = await self.db_session.execute(query, {
                        'pair': pair,
                        'timeframe': timeframe
                    })

                    rows = result.fetchall()

                    if rows:
                        # Convert to OHLC objects and reverse (oldest first)
                        candles = []
                        for row in reversed(rows):
                            candle = OHLC(
                                pair=row.pair,
                                timeframe=row.timeframe,
                                timestamp=row.open_time,
                                open=float(row.open_price),
                                high=float(row.high_price),
                                low=float(row.low_price),
                                close=float(row.close_price),
                                volume=float(row.volume),
                                trade_count=int(row.num_trades) if row.num_trades else 0
                            )
                            candles.append(candle)

                        # Store in historical candles buffer
                        self.historical_candles[pair][timeframe] = candles

                        logger.info(
                            f"Preloaded {len(candles)} historical candles: {pair} {timeframe} "
                            f"({candles[0].timestamp.strftime('%Y-%m-%d %H:%M')} to "
                            f"{candles[-1].timestamp.strftime('%Y-%m-%d %H:%M')})"
                        )
                    else:
                        logger.warning(f"No historical candles found for {pair} {timeframe}")

            logger.info(f"Historical candle preload complete for {len(self.pairs)} pairs")

        except Exception as e:
            logger.error(f"Failed to preload historical candles: {e}", exc_info=True)

    async def _persist_features_to_database(self, pair: str):
        """
        Compute and persist 90-feature vector to engineered_features table.

        Requires at least 50 candles from each timeframe (1m, 5m, 15m).

        Args:
            pair: Trading pair
        """
        if not self.db_session or not self.compute_features or not self.feature_engineer:
            return

        try:
            # Check if we have enough historical candles
            candles_1m = self.historical_candles[pair].get("1m", [])
            candles_5m = self.historical_candles[pair].get("5m", [])
            candles_15m = self.historical_candles[pair].get("15m", [])

            if len(candles_1m) < 50 or len(candles_5m) < 50 or len(candles_15m) < 50:
                logger.debug(
                    f"Insufficient candles for feature computation: "
                    f"{pair} 1m={len(candles_1m)}, 5m={len(candles_5m)}, 15m={len(candles_15m)}"
                )
                return

            # Compute 90-feature vector
            feature_vector = self.feature_engineer.calculate_features(
                candles_1m=candles_1m,
                candles_5m=candles_5m,
                candles_15m=candles_15m,
                pair=pair
            )

            if not feature_vector:
                logger.warning(f"Feature computation failed for {pair}")
                return

            # Persist to engineered_features table
            query = text("""
                INSERT INTO engineered_features (
                    pair,
                    features_vector,
                    computed_at
                ) VALUES (
                    :pair,
                    :features_vector,
                    :computed_at
                )
            """)

            # Strip timezone for PostgreSQL TIMESTAMP column (UTC timezone-naive)
            computed_at = feature_vector.timestamp.replace(tzinfo=None) if feature_vector.timestamp.tzinfo else feature_vector.timestamp

            # Replace NaN with None using numpy before converting to list (JSON doesn't support NaN)
            import numpy as np
            features_clean = np.where(np.isnan(feature_vector.features), None, feature_vector.features).tolist()

            await self.db_session.execute(query, {
                'pair': pair,
                'features_vector': json.dumps({
                    'features': features_clean,
                    'feature_names': feature_vector.feature_names
                }),
                'computed_at': computed_at
            })

            await self.db_session.commit()
            self.features_computed += 1

            logger.debug(
                f"Persisted 90-feature vector to DB: {pair} "
                f"@ {feature_vector.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(f"Failed to persist features to database: {e}", exc_info=True)
            await self.db_session.rollback()

    async def _finalize_candle(self, key: tuple):
        """
        Finalize current candle and emit NEW_CANDLE event.

        Args:
            key: (pair, timeframe) tuple
        """
        pair, timeframe = key

        try:
            # Get builder
            builder = self.builders.get(key)
            if not builder:
                return

            # Finalize candle
            candle = builder.finalize()

            logger.info(
                f"Candle closed: {pair} {timeframe} "
                f"O:{candle.open:.2f} H:{candle.high:.2f} "
                f"L:{candle.low:.2f} C:{candle.close:.2f} "
                f"V:{candle.volume:.4f} ({candle.trade_count} trades)"
            )

            # PERSIST TO DATABASE BEFORE EMITTING EVENT
            await self._persist_candle_to_database(candle, pair, timeframe)

            # Add to historical candles for feature computation (keep last 100 candles)
            if self.compute_features:
                self.historical_candles[pair][timeframe].append(candle)
                if len(self.historical_candles[pair][timeframe]) > 100:
                    self.historical_candles[pair][timeframe].pop(0)

                # Compute and persist features (only on 1m candles to avoid redundancy)
                if timeframe == "1m":
                    await self._persist_features_to_database(pair)

            # Emit NEW_CANDLE event
            await self.event_queue.put({
                "type": "NEW_CANDLE",
                "pair": pair,
                "timeframe": timeframe,
                "candle": {
                    "timestamp": candle.timestamp.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "trade_count": candle.trade_count
                }
            })

            self.candles_generated += 1

            # Create new builder for next period
            new_start_time = self._get_candle_start_time(timeframe)
            self.builders[key] = CandleBuilder(
                pair=pair,
                timeframe=timeframe,
                start_time=new_start_time
            )
            self.last_candle_times[key] = new_start_time

        except Exception as e:
            logger.error(f"Error finalizing candle {key}: {e}", exc_info=True)

    async def _candle_finalization_loop(self):
        """
        Background loop to check and finalize candles periodically.

        Runs every second to ensure candles are finalized on time.
        """
        logger.info("Candle finalization loop started")

        while self.running:
            try:
                # Check all builders for period changes
                for key in list(self.builders.keys()):
                    await self._check_candle_period(key)

                # Sleep 1 second
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in finalization loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait longer on error

        logger.info("Candle finalization loop stopped")

    async def stop(self):
        """Stop the candle generator."""
        logger.info("Stopping live candle generator...")

        self.running = False

        # Stop WebSocket
        if self.websocket_client:
            await self.websocket_client.stop()

        logger.info(
            f"Live candle generator stopped. "
            f"Stats: {self.trades_processed} trades processed, "
            f"{self.candles_generated} candles generated, "
            f"{self.candles_persisted} candles persisted to database, "
            f"{self.features_computed} feature vectors computed"
        )

    def get_stats(self) -> Dict:
        """Get generator statistics."""
        return {
            "running": self.running,
            "pairs": self.pairs,
            "timeframes": self.timeframes,
            "trades_processed": self.trades_processed,
            "candles_generated": self.candles_generated,
            "active_builders": len(self.builders),
            "websocket_stats": (
                self.websocket_client.get_stats()
                if self.websocket_client
                else None
            )
        }


# Example usage and testing
if __name__ == "__main__":
    async def main():
        """Test live candle generator."""
        print("\n" + "=" * 60)
        print("  Live Candle Generator Test")
        print("=" * 60 + "\n")

        # Create event queue
        event_queue = asyncio.Queue()

        # Create generator
        generator = LiveCandleGenerator(
            pairs=["BTCZAR"],
            event_queue=event_queue,
            timeframes=["1m", "5m"]
        )

        # Event consumer task
        async def consume_events():
            """Consume and print events."""
            while True:
                event = await event_queue.get()
                event_type = event['type']

                if event_type == 'NEW_CANDLE':
                    candle = event['candle']
                    print(
                        f"\n[NEW CANDLE] {event['pair']} {event['timeframe']}: "
                        f"O:{candle['open']:.2f} H:{candle['high']:.2f} "
                        f"L:{candle['low']:.2f} C:{candle['close']:.2f}"
                    )

                elif event_type == 'PRICE_UPDATE':
                    print(
                        f"[PRICE] {event['pair']}: {event['price']:.2f}",
                        end='\r'
                    )

        try:
            # Start generator
            await generator.start()

            # Start event consumer
            consumer_task = asyncio.create_task(consume_events())

            # Run for 5 minutes
            print("Running for 5 minutes... (Ctrl+C to stop)")
            await asyncio.sleep(300)

        except KeyboardInterrupt:
            print("\n\nStopping...")

        finally:
            # Stop generator
            await generator.stop()

            # Print stats
            stats = generator.get_stats()
            print("\n" + "=" * 60)
            print("  Statistics")
            print("=" * 60)
            print(f"  Trades Processed: {stats['trades_processed']}")
            print(f"  Candles Generated: {stats['candles_generated']}")
            print(f"  Active Builders: {stats['active_builders']}")
            print("=" * 60 + "\n")

    asyncio.run(main())
