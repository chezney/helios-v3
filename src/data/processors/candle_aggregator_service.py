"""
Candle Aggregator Service

Automatically aggregates 1m candles to higher timeframes (5m, 15m, 1h, 4h, 1d)
Runs as a background task in the autonomous engine.

Helios V3.0 - Tier 1 Data Foundation
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="candle_aggregator")


class CandleAggregatorService:
    """Background service to aggregate candles to higher timeframes."""

    def __init__(self, pairs: List[str] = None):
        """
        Initialize the candle aggregator service.

        Args:
            pairs: List of pairs to aggregate (default: ['BTCZAR', 'ETHZAR', 'SOLZAR'])
        """
        self.pairs = pairs or ['BTCZAR', 'ETHZAR', 'SOLZAR']
        self.running = False
        self.last_aggregation = {}

        # Timeframe configuration
        self.timeframes = {
            '5m': {'source': '1m', 'minutes': 5, 'interval_minutes': 5},
            '15m': {'source': '1m', 'minutes': 15, 'interval_minutes': 15},
            '1h': {'source': '1m', 'minutes': 60, 'interval_minutes': 60},
            '4h': {'source': '1h', 'minutes': 240, 'interval_minutes': 240},
            '1d': {'source': '1h', 'minutes': 1440, 'interval_minutes': 1440},
        }

    async def start(self):
        """Start the background aggregation service."""
        self.running = True
        logger.info(f"Candle aggregator service started for pairs: {', '.join(self.pairs)}")

        # Run aggregation loop
        while self.running:
            try:
                await self._aggregate_cycle()
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                logger.error(f"Aggregation cycle error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def stop(self):
        """Stop the background aggregation service."""
        self.running = False
        logger.info("Candle aggregator service stopped")

    async def _aggregate_cycle(self):
        """Run one aggregation cycle for all pairs and timeframes."""
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            for pair in self.pairs:
                for target_tf, config in self.timeframes.items():
                    # Check if it's time to aggregate this timeframe
                    if self._should_aggregate(pair, target_tf, config):
                        await self._aggregate_timeframe(conn, pair, config['source'], target_tf, config['minutes'])
        finally:
            await conn.close()

    def _should_aggregate(self, pair: str, timeframe: str, config: Dict) -> bool:
        """
        Determine if we should aggregate this timeframe now.

        For efficiency, we don't aggregate every cycle:
        - 5m, 15m: every cycle (5 minutes)
        - 1h: every 15 minutes
        - 4h, 1d: every hour
        """
        key = f"{pair}_{timeframe}"
        last_run = self.last_aggregation.get(key)

        if last_run is None:
            return True  # First run

        elapsed = (datetime.utcnow() - last_run).total_seconds() / 60  # minutes

        # Aggregation frequency rules
        if timeframe in ['5m', '15m']:
            return elapsed >= 5
        elif timeframe == '1h':
            return elapsed >= 15
        else:  # 4h, 1d
            return elapsed >= 60

    async def _aggregate_timeframe(
        self,
        conn: asyncpg.Connection,
        pair: str,
        source_tf: str,
        target_tf: str,
        target_minutes: int
    ):
        """
        Aggregate candles from source to target timeframe.

        Only aggregates recent incomplete periods to avoid reprocessing old data.
        """
        try:
            # Get the most recent target candle timestamp
            latest_target = await conn.fetchval("""
                SELECT MAX(open_time)
                FROM market_ohlc
                WHERE pair = $1 AND timeframe = $2
            """, pair, target_tf)

            # Determine lookback period
            # We need to look back far enough to catch incomplete periods
            lookback_hours = max(24, target_minutes // 60 * 2)
            lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)

            # If we have recent target candles, only look back from there
            if latest_target:
                lookback_time = min(lookback_time, latest_target - timedelta(minutes=target_minutes))

            # Fetch source candles since lookback time
            source_candles = await conn.fetch("""
                SELECT open_time, close_time, open_price, high_price, low_price, close_price, volume
                FROM market_ohlc
                WHERE pair = $1 AND timeframe = $2 AND open_time >= $3
                ORDER BY open_time ASC
            """, pair, source_tf, lookback_time)

            if not source_candles:
                return

            # Group and aggregate
            aggregated = self._group_and_aggregate(source_candles, pair, target_tf, target_minutes)

            # Insert aggregated candles
            if aggregated:
                inserted = await self._insert_candles(conn, aggregated)
                if inserted > 0:
                    logger.info(f"Aggregated {pair} {source_tf}->{target_tf}: {inserted} new candles")

            # Update last aggregation time
            self.last_aggregation[f"{pair}_{target_tf}"] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Failed to aggregate {pair} {source_tf}->{target_tf}: {e}")

    def _group_and_aggregate(
        self,
        candles: List[Dict],
        pair: str,
        timeframe: str,
        target_minutes: int
    ) -> List[Dict]:
        """Group source candles by target timeframe and aggregate."""
        aggregated = []
        current_group = []
        current_period_start = None

        for row in candles:
            open_time = row['open_time']

            # Calculate target period start
            minutes_since_epoch = int(open_time.timestamp() / 60)
            period_start_minutes = (minutes_since_epoch // target_minutes) * target_minutes
            period_start = datetime.utcfromtimestamp(period_start_minutes * 60)

            # Start new group if period changed
            if current_period_start is None:
                current_period_start = period_start
                current_group = [row]
            elif period_start != current_period_start:
                # Aggregate current group
                if current_group:
                    agg_candle = self._aggregate_group(
                        pair, timeframe, current_period_start, current_group, target_minutes
                    )
                    aggregated.append(agg_candle)

                # Start new group
                current_period_start = period_start
                current_group = [row]
            else:
                # Add to current group
                current_group.append(row)

        # Aggregate final group (but only if it's complete)
        if current_group and len(current_group) >= 1:
            # Don't aggregate the most recent incomplete period
            period_end = current_period_start + timedelta(minutes=target_minutes)
            if datetime.utcnow() >= period_end:
                agg_candle = self._aggregate_group(
                    pair, timeframe, current_period_start, current_group, target_minutes
                )
                aggregated.append(agg_candle)

        return aggregated

    def _aggregate_group(
        self,
        pair: str,
        timeframe: str,
        period_start: datetime,
        candles: List[Dict],
        target_minutes: int
    ) -> Dict:
        """Aggregate a group of candles into one candle."""
        close_time = period_start + timedelta(minutes=target_minutes)

        return {
            'pair': pair,
            'timeframe': timeframe,
            'open_time': period_start,
            'close_time': close_time,
            'open_price': candles[0]['open_price'],
            'high_price': max(c['high_price'] for c in candles),
            'low_price': min(c['low_price'] for c in candles),
            'close_price': candles[-1]['close_price'],
            'volume': sum(c['volume'] for c in candles)
        }

    async def _insert_candles(self, conn: asyncpg.Connection, candles: List[Dict]) -> int:
        """Insert aggregated candles, return count of new inserts."""
        query = """
            INSERT INTO market_ohlc (
                pair, timeframe, open_time, close_time,
                open_price, high_price, low_price, close_price, volume
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (pair, timeframe, open_time)
            DO UPDATE SET
                close_time = EXCLUDED.close_time,
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume
        """

        inserted = 0
        for candle in candles:
            await conn.execute(
                query,
                candle['pair'],
                candle['timeframe'],
                candle['open_time'],
                candle['close_time'],
                candle['open_price'],
                candle['high_price'],
                candle['low_price'],
                candle['close_price'],
                candle['volume']
            )
            inserted += 1

        return inserted

    async def aggregate_now(self, pair: Optional[str] = None):
        """
        Trigger immediate aggregation for all timeframes.

        Args:
            pair: Optional specific pair to aggregate (default: all pairs)
        """
        pairs_to_aggregate = [pair] if pair else self.pairs

        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            for p in pairs_to_aggregate:
                for target_tf, config in self.timeframes.items():
                    await self._aggregate_timeframe(conn, p, config['source'], target_tf, config['minutes'])
        finally:
            await conn.close()
