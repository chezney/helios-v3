"""
Helios Trading System V3.0 - Tier 1: Multi-Timeframe Candle Aggregator
Aggregates real-time trades into OHLC candles for 1min, 5min, 15min timeframes
Following PRD Section 8: Multi-Timeframe Aggregation
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np

from src.utils.logger import get_logger
from src.data.collectors import MarketTick

logger = get_logger(__name__, component="tier1_candles")

# Database writer imported dynamically to avoid circular imports


@dataclass
class OHLC:
    """OHLC candle data structure"""
    pair: str
    timeframe: str  # "1m", "5m", "15m"
    timestamp: datetime  # Start of candle period
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count
        }


@dataclass
class CandleBuilder:
    """Builds a single OHLC candle from incoming trades"""
    pair: str
    timeframe: str
    start_time: datetime
    open: float = 0.0
    high: float = 0.0
    low: float = float('inf')
    close: float = 0.0
    volume: float = 0.0
    trade_count: int = 0
    first_trade: bool = True

    def add_trade(self, price: float, quantity: float):
        """Add a trade to this candle"""
        if self.first_trade:
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.first_trade = False
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price

        self.volume += quantity
        self.trade_count += 1

    def finalize(self) -> OHLC:
        """Finalize and return complete OHLC candle"""
        # Handle case where no trades occurred
        if self.first_trade:
            # Use previous close or 0
            self.open = self.close if self.close > 0 else 0.0
            self.high = self.open
            self.low = self.open

        return OHLC(
            pair=self.pair,
            timeframe=self.timeframe,
            timestamp=self.start_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            trade_count=self.trade_count
        )


class MultiTimeframeAggregator:
    """
    Aggregates real-time trades into OHLC candles for multiple timeframes.

    Features:
    - Simultaneous aggregation for 1min, 5min, 15min
    - Automatic candle finalization on timeframe boundaries
    - Callback system for completed candles
    - In-memory buffer for recent candles
    - Thread-safe operation
    """

    TIMEFRAMES = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15)
    }

    def __init__(
        self,
        pairs: List[str],
        on_candle_complete: Optional[Callable[[OHLC], None]] = None,
        buffer_size: int = 1000,
        db_writer=None  # DatabaseWriter instance (optional)
    ):
        """
        Initialize multi-timeframe aggregator.

        Args:
            pairs: Trading pairs to track (e.g., ["BTCZAR", "ETHZAR"])
            on_candle_complete: Callback when a candle is finalized
            buffer_size: Number of recent candles to keep in memory per pair/timeframe
            db_writer: Optional DatabaseWriter for persistence
        """
        self.pairs = pairs
        self.on_candle_complete = on_candle_complete
        self.buffer_size = buffer_size
        self.db_writer = db_writer

        # Current candle builders: {pair: {timeframe: CandleBuilder}}
        self.current_candles: Dict[str, Dict[str, CandleBuilder]] = defaultdict(dict)

        # Completed candles buffer: {pair: {timeframe: [OHLC, ...]}}
        self.candle_buffer: Dict[str, Dict[str, List[OHLC]]] = defaultdict(lambda: defaultdict(list))

        # Last known prices for handling gaps
        self.last_prices: Dict[str, float] = {}

        # Statistics
        self.total_trades_processed = 0
        self.total_candles_created = 0

        # Running flag
        self.running = False

        logger.info(f"MultiTimeframeAggregator initialized for {len(pairs)} pairs, {len(self.TIMEFRAMES)} timeframes")

    def _get_candle_start_time(self, timestamp: datetime, timeframe: str) -> datetime:
        """
        Get the start time of the candle period for a given timestamp.

        Example:
            timestamp: 2025-01-15 14:23:47
            timeframe: 5m
            returns: 2025-01-15 14:20:00
        """
        delta = self.TIMEFRAMES[timeframe]
        minutes = int(delta.total_seconds() / 60)

        # Floor to the nearest timeframe boundary
        floored_minute = (timestamp.minute // minutes) * minutes

        return timestamp.replace(minute=floored_minute, second=0, microsecond=0)

    def _should_finalize_candle(self, builder: CandleBuilder, current_time: datetime) -> bool:
        """Check if current candle should be finalized"""
        delta = self.TIMEFRAMES[builder.timeframe]
        candle_end_time = builder.start_time + delta

        return current_time >= candle_end_time

    async def process_trade(self, tick: MarketTick):
        """
        Process incoming trade and update all timeframes.

        Args:
            tick: Market tick from WebSocket
        """
        if tick.pair not in self.pairs:
            return

        # Update last known price
        self.last_prices[tick.pair] = tick.price

        # Process for each timeframe
        for timeframe in self.TIMEFRAMES.keys():
            await self._process_trade_for_timeframe(tick, timeframe)

        self.total_trades_processed += 1

    async def _process_trade_for_timeframe(self, tick: MarketTick, timeframe: str):
        """Process trade for a specific timeframe"""
        candle_start = self._get_candle_start_time(tick.timestamp, timeframe)

        # Get or create current candle builder
        if timeframe not in self.current_candles[tick.pair]:
            # Create new candle builder
            self.current_candles[tick.pair][timeframe] = CandleBuilder(
                pair=tick.pair,
                timeframe=timeframe,
                start_time=candle_start
            )

        current_builder = self.current_candles[tick.pair][timeframe]

        # Check if we need to finalize current candle and start new one
        if self._should_finalize_candle(current_builder, tick.timestamp):
            # Finalize current candle
            completed_candle = current_builder.finalize()

            # Save to database if writer available
            if self.db_writer:
                try:
                    await self.db_writer.save_candle(completed_candle)
                except Exception as e:
                    logger.error(f"Error saving candle to database: {e}", exc_info=True)

            # Store in buffer
            self._add_to_buffer(completed_candle)

            # Call callback
            if self.on_candle_complete:
                try:
                    await asyncio.create_task(self.on_candle_complete(completed_candle))
                except Exception as e:
                    logger.error(f"Error in candle callback: {e}", exc_info=True)

            self.total_candles_created += 1

            logger.debug(
                f"Candle finalized: {completed_candle.pair} {completed_candle.timeframe} - "
                f"O:{completed_candle.open:,.2f} H:{completed_candle.high:,.2f} "
                f"L:{completed_candle.low:,.2f} C:{completed_candle.close:,.2f} "
                f"V:{completed_candle.volume:,.4f} T:{completed_candle.trade_count}"
            )

            # Create new candle builder
            self.current_candles[tick.pair][timeframe] = CandleBuilder(
                pair=tick.pair,
                timeframe=timeframe,
                start_time=candle_start
            )
            current_builder = self.current_candles[tick.pair][timeframe]

        # Add trade to current candle
        current_builder.add_trade(tick.price, tick.quantity)

    def _add_to_buffer(self, candle: OHLC):
        """Add completed candle to buffer with size limit"""
        buffer = self.candle_buffer[candle.pair][candle.timeframe]
        buffer.append(candle)

        # Trim buffer if exceeds size
        if len(buffer) > self.buffer_size:
            buffer.pop(0)

    def get_recent_candles(
        self,
        pair: str,
        timeframe: str,
        limit: int = 100
    ) -> List[OHLC]:
        """
        Get recent completed candles.

        Args:
            pair: Trading pair
            timeframe: Timeframe (1m, 5m, 15m)
            limit: Maximum number of candles to return

        Returns:
            List of OHLC candles, most recent last
        """
        if pair not in self.candle_buffer:
            return []

        if timeframe not in self.candle_buffer[pair]:
            return []

        buffer = self.candle_buffer[pair][timeframe]
        return buffer[-limit:] if len(buffer) > limit else buffer.copy()

    def get_current_candle(self, pair: str, timeframe: str) -> Optional[OHLC]:
        """
        Get current incomplete candle.

        Args:
            pair: Trading pair
            timeframe: Timeframe

        Returns:
            Current OHLC candle (incomplete) or None
        """
        if pair not in self.current_candles:
            return None

        if timeframe not in self.current_candles[pair]:
            return None

        builder = self.current_candles[pair][timeframe]
        return builder.finalize()  # Returns snapshot of current state

    async def force_finalize_all(self):
        """Force finalize all current candles (useful for shutdown)"""
        logger.info("Force finalizing all current candles...")

        for pair in self.current_candles:
            for timeframe in self.current_candles[pair]:
                builder = self.current_candles[pair][timeframe]

                if not builder.first_trade:  # Only finalize if has trades
                    completed_candle = builder.finalize()
                    self._add_to_buffer(completed_candle)

                    if self.on_candle_complete:
                        try:
                            await self.on_candle_complete(completed_candle)
                        except Exception as e:
                            logger.error(f"Error in candle callback: {e}", exc_info=True)

                    self.total_candles_created += 1

        self.current_candles.clear()
        logger.info("All candles finalized")

    def get_stats(self) -> Dict:
        """Get aggregator statistics"""
        total_buffered = sum(
            len(self.candle_buffer[pair][tf])
            for pair in self.candle_buffer
            for tf in self.candle_buffer[pair]
        )

        return {
            "pairs": self.pairs,
            "timeframes": list(self.TIMEFRAMES.keys()),
            "total_trades_processed": self.total_trades_processed,
            "total_candles_created": self.total_candles_created,
            "buffered_candles": total_buffered,
            "current_candles": {
                pair: list(self.current_candles[pair].keys())
                for pair in self.current_candles
            }
        }


# Example usage and testing
if __name__ == "__main__":
    from src.data.collectors import VALRWebSocketClient

    async def handle_candle(candle: OHLC):
        """Example candle handler"""
        print(
            f"[CANDLE] {candle.pair} {candle.timeframe} @ {candle.timestamp.strftime('%H:%M:%S')} - "
            f"O:R{candle.open:,.2f} H:R{candle.high:,.2f} L:R{candle.low:,.2f} C:R{candle.close:,.2f} "
            f"V:{candle.volume:,.4f} T:{candle.trade_count}"
        )

    async def main():
        """Test candle aggregator with live WebSocket data"""
        print("\n" + "=" * 80)
        print("  Multi-Timeframe Candle Aggregator Test")
        print("=" * 80 + "\n")

        # Create aggregator
        aggregator = MultiTimeframeAggregator(
            pairs=["BTCZAR"],
            on_candle_complete=handle_candle
        )

        # Create WebSocket client with aggregator callback
        async def handle_trade(tick: MarketTick):
            """Process trades through aggregator"""
            await aggregator.process_trade(tick)

        client = VALRWebSocketClient(
            pairs=["BTCZAR"],
            on_trade=handle_trade
        )

        try:
            # Start WebSocket client
            print("Starting WebSocket client and candle aggregation...")
            print("Will aggregate trades into 1min, 5min, 15min candles\n")

            # Run for 3 minutes to see at least one 1min candle complete
            await asyncio.wait_for(client.start(), timeout=180)

        except asyncio.TimeoutError:
            print("\n\nTest completed (3 minutes)")
            await client.stop()
            await aggregator.force_finalize_all()
        except KeyboardInterrupt:
            print("\n\nStopping...")
            await client.stop()
            await aggregator.force_finalize_all()

        # Print stats
        stats = aggregator.get_stats()
        print("\n" + "=" * 80)
        print("  Statistics")
        print("=" * 80)
        print(f"  Trades Processed: {stats['total_trades_processed']}")
        print(f"  Candles Created: {stats['total_candles_created']}")
        print(f"  Buffered Candles: {stats['buffered_candles']}")

        # Show recent candles for each timeframe
        for tf in ["1m", "5m", "15m"]:
            candles = aggregator.get_recent_candles("BTCZAR", tf, limit=5)
            print(f"\n  Recent {tf} Candles: {len(candles)}")
            for c in candles[-3:]:  # Last 3
                print(f"    {c.timestamp.strftime('%H:%M:%S')} - "
                      f"O:R{c.open:,.0f} H:R{c.high:,.0f} L:R{c.low:,.0f} C:R{c.close:,.0f}")

        print("=" * 80 + "\n")

    asyncio.run(main())
