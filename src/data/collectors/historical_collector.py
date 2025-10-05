"""
Historical Data Collector

Fetches historical trades from VALR API and aggregates into OHLC candles.
Part of Phase 1, Week 5: Historical Data Backfill.
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import asyncpg

from config.settings import settings
from src.utils.logger import get_logger
from src.data.processors.candle_aggregator import OHLC
from src.data.processors.feature_engineering import FeatureEngineer

logger = get_logger(__name__, component="historical_collector")


@dataclass
class Trade:
    """Trade data from VALR API"""
    pair: str
    price: float
    quantity: float
    traded_at: datetime
    taker_side: str  # BUY or SELL
    sequence_id: int
    id: str


class HistoricalDataCollector:
    """
    Collects historical trade data from VALR and builds OHLC candles.

    VALR API Endpoint: GET /v1/public/{pair}/trades
    Rate Limit: 30 second cache TTL (can query ~2 times per minute safely)

    Strategy:
    1. Fetch trades in batches (limit=100 max per request)
    2. Aggregate trades into 1-minute candles
    3. Store candles in database
    4. Calculate and store features
    """

    def __init__(self):
        self.base_url = "https://api.valr.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.feature_engineer = FeatureEngineer()

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def fetch_recent_trades(
        self,
        pair: str,
        limit: int = 100,
        skip: int = 0
    ) -> List[Trade]:
        """
        Fetch recent trades from VALR API.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            limit: Number of trades to fetch (max 100)
            skip: Number of trades to skip (for pagination)

        Returns:
            List of Trade objects
        """
        url = f"{self.base_url}/v1/public/{pair}/trades"
        params = {"limit": min(limit, 100)}
        if skip > 0:
            params["skip"] = skip

        try:
            async with self.session.get(url, params=params, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"VALR API error: {response.status}")
                    return []

                data = await response.json()

                trades = []
                for trade_data in data:
                    try:
                        trade = Trade(
                            pair=pair,
                            price=float(trade_data["price"]),
                            quantity=float(trade_data["quantity"]),
                            traded_at=datetime.fromisoformat(
                                trade_data["tradedAt"].replace("Z", "+00:00")
                            ),
                            taker_side=trade_data["takerSide"],
                            sequence_id=int(trade_data["sequenceId"]),
                            id=trade_data["id"]
                        )
                        trades.append(trade)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse trade: {e}")
                        continue

                logger.info(f"Fetched {len(trades)} trades for {pair}")
                return trades

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching trades for {pair}")
            return []
        except Exception as e:
            logger.error(f"Error fetching trades for {pair}: {e}")
            return []

    def aggregate_trades_to_candles(
        self,
        trades: List[Trade],
        timeframe: str = "1m"
    ) -> List[OHLC]:
        """
        Aggregate trades into OHLC candles.

        Args:
            trades: List of trades (sorted by time, oldest first)
            timeframe: Candle timeframe ('1m', '5m', '15m')

        Returns:
            List of OHLC candles
        """
        if not trades:
            return []

        # Determine candle duration
        if timeframe == "1m":
            candle_duration = timedelta(minutes=1)
        elif timeframe == "5m":
            candle_duration = timedelta(minutes=5)
        elif timeframe == "15m":
            candle_duration = timedelta(minutes=15)
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        # Sort trades by time (oldest first)
        trades = sorted(trades, key=lambda t: t.traded_at)

        candles = []
        current_candle_start = self._floor_time(trades[0].traded_at, timeframe)
        current_candle_trades = []

        for trade in trades:
            trade_candle_start = self._floor_time(trade.traded_at, timeframe)

            # If trade belongs to new candle, finalize current candle
            if trade_candle_start > current_candle_start:
                if current_candle_trades:
                    candle = self._create_candle_from_trades(
                        current_candle_trades,
                        current_candle_start,
                        timeframe
                    )
                    if candle:
                        candles.append(candle)

                # Start new candle
                current_candle_start = trade_candle_start
                current_candle_trades = [trade]
            else:
                current_candle_trades.append(trade)

        # Finalize last candle
        if current_candle_trades:
            candle = self._create_candle_from_trades(
                current_candle_trades,
                current_candle_start,
                timeframe
            )
            if candle:
                candles.append(candle)

        logger.info(f"Aggregated {len(trades)} trades into {len(candles)} {timeframe} candles")
        return candles

    def _floor_time(self, dt: datetime, timeframe: str) -> datetime:
        """Floor datetime to candle boundary"""
        if timeframe == "1m":
            return dt.replace(second=0, microsecond=0)
        elif timeframe == "5m":
            minute = (dt.minute // 5) * 5
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "15m":
            minute = (dt.minute // 15) * 15
            return dt.replace(minute=minute, second=0, microsecond=0)
        else:
            return dt

    def _create_candle_from_trades(
        self,
        trades: List[Trade],
        candle_start: datetime,
        timeframe: str
    ) -> Optional[OHLC]:
        """Create OHLC candle from list of trades"""
        if not trades:
            return None

        # Sort by time
        trades = sorted(trades, key=lambda t: t.traded_at)

        open_price = trades[0].price
        close_price = trades[-1].price
        high_price = max(t.price for t in trades)
        low_price = min(t.price for t in trades)
        volume = sum(t.quantity for t in trades)
        trade_count = len(trades)

        return OHLC(
            pair=trades[0].pair,
            timeframe=timeframe,
            timestamp=candle_start,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_count=trade_count
        )

    async def backfill_historical_data(
        self,
        pair: str,
        days: int = 90,
        db_pool: asyncpg.Pool = None
    ) -> Dict[str, Any]:
        """
        Backfill historical data for a trading pair.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            days: Number of days to backfill
            db_pool: Database connection pool

        Returns:
            Dict with backfill statistics
        """
        logger.info(f"Starting backfill for {pair} - {days} days")
        logger.warning("⚠️ LIMITATION: VALR /v1/public/{pair}/trades only provides recent trades")
        logger.warning("    For true 90-day backfill, would need VALR historical data API or")
        logger.warning("    alternative data provider. Currently fetching available recent trades.")

        stats = {
            "pair": pair,
            "requested_days": days,
            "trades_fetched": 0,
            "candles_created": 0,
            "features_calculated": 0,
            "start_time": datetime.utcnow(),
            "status": "in_progress"
        }

        try:
            # Fetch recent trades (VALR API limitation - only recent data available)
            all_trades = []

            # Fetch in batches with pagination
            for batch in range(10):  # Fetch up to 1000 recent trades
                trades = await self.fetch_recent_trades(
                    pair=pair,
                    limit=100,
                    skip=batch * 100
                )

                if not trades:
                    break

                all_trades.extend(trades)
                stats["trades_fetched"] = len(all_trades)

                # Rate limiting - wait between requests
                await asyncio.sleep(2)  # 30 requests per minute safe limit

            if not all_trades:
                logger.error(f"No trades fetched for {pair}")
                stats["status"] = "failed"
                return stats

            # Aggregate into 1m candles
            candles_1m = self.aggregate_trades_to_candles(all_trades, timeframe="1m")
            stats["candles_created"] = len(candles_1m)

            # Store candles in database
            if db_pool and candles_1m:
                await self._store_candles(db_pool, candles_1m)
                logger.info(f"Stored {len(candles_1m)} candles in database")

            # Calculate and store features
            if len(candles_1m) >= 50:  # Need at least 50 candles for features
                features_count = await self._calculate_and_store_features(
                    db_pool,
                    candles_1m,
                    pair
                )
                stats["features_calculated"] = features_count

            stats["end_time"] = datetime.utcnow()
            stats["duration_seconds"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            stats["status"] = "completed"

            logger.info(f"Backfill complete for {pair}: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Backfill failed for {pair}: {e}", exc_info=True)
            stats["status"] = "failed"
            stats["error"] = str(e)
            return stats

    async def _store_candles(self, db_pool: asyncpg.Pool, candles: List[OHLC]):
        """Store candles in database"""
        async with db_pool.acquire() as conn:
            for candle in candles:
                # Convert timezone-aware datetime to naive (PostgreSQL TIMESTAMP type)
                timestamp_naive = candle.timestamp.replace(tzinfo=None) if candle.timestamp.tzinfo else candle.timestamp

                # Calculate close_time based on timeframe
                close_time_naive = timestamp_naive + timedelta(minutes={
                    '1m': 1, '5m': 5, '15m': 15
                }.get(candle.timeframe, 1))

                await conn.execute("""
                    INSERT INTO market_ohlc
                    (pair, timeframe, open_time, close_time, open_price, high_price, low_price, close_price, volume, num_trades)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (pair, timeframe, open_time) DO UPDATE SET
                        close_time = EXCLUDED.close_time,
                        open_price = EXCLUDED.open_price,
                        high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price,
                        close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume,
                        num_trades = EXCLUDED.num_trades
                """, candle.pair, candle.timeframe, timestamp_naive, close_time_naive,
                    candle.open, candle.high, candle.low, candle.close,
                    candle.volume, candle.trade_count)

    async def _calculate_and_store_features(
        self,
        db_pool: asyncpg.Pool,
        candles_1m: List[OHLC],
        pair: str
    ) -> int:
        """Calculate features for candles and store in database"""
        # Need 50 candles for each timeframe
        # Generate 5m and 15m candles from 1m
        candles_5m = self._aggregate_candles(candles_1m, "5m")
        candles_15m = self._aggregate_candles(candles_1m, "15m")

        features_count = 0

        # Calculate features for windows of 50 candles
        for i in range(50, len(candles_1m)):
            if i >= len(candles_5m) or i >= len(candles_15m):
                continue

            feature_vector = self.feature_engineer.calculate_features(
                candles_1m=candles_1m[i-50:i],
                candles_5m=candles_5m[max(0, i-50):i],
                candles_15m=candles_15m[max(0, i-50):i],
                pair=pair
            )

            if feature_vector and db_pool:
                # Convert timezone-aware datetime to naive
                timestamp_naive = feature_vector.timestamp.replace(tzinfo=None) if feature_vector.timestamp.tzinfo else feature_vector.timestamp

                # Store features in database (PRD schema: engineered_features with JSONB)
                async with db_pool.acquire() as conn:
                    import json
                    features_jsonb = json.dumps({
                        'features': feature_vector.features.tolist(),
                        'feature_names': feature_vector.feature_names
                    })

                    await conn.execute("""
                        INSERT INTO engineered_features
                        (pair, features_vector, computed_at)
                        VALUES ($1, $2::jsonb, $3)
                        ON CONFLICT DO NOTHING
                    """, feature_vector.pair, features_jsonb, timestamp_naive)

                features_count += 1

        return features_count

    def _aggregate_candles(self, candles_1m: List[OHLC], target_timeframe: str) -> List[OHLC]:
        """Aggregate 1m candles into higher timeframes"""
        if target_timeframe == "1m":
            return candles_1m

        if target_timeframe == "5m":
            minutes = 5
        elif target_timeframe == "15m":
            minutes = 15
        else:
            return []

        aggregated = []
        current_group = []
        current_start = None

        for candle in candles_1m:
            candle_start = self._floor_time(candle.timestamp, target_timeframe)

            if current_start is None:
                current_start = candle_start

            if candle_start == current_start:
                current_group.append(candle)
            else:
                # Finalize current group
                if current_group:
                    agg_candle = self._merge_candles(current_group, target_timeframe)
                    if agg_candle:
                        aggregated.append(agg_candle)

                current_start = candle_start
                current_group = [candle]

        # Finalize last group
        if current_group:
            agg_candle = self._merge_candles(current_group, target_timeframe)
            if agg_candle:
                aggregated.append(agg_candle)

        return aggregated

    def _merge_candles(self, candles: List[OHLC], timeframe: str) -> Optional[OHLC]:
        """Merge multiple candles into one"""
        if not candles:
            return None

        return OHLC(
            pair=candles[0].pair,
            timeframe=timeframe,
            timestamp=candles[0].timestamp,
            open=candles[0].open,
            high=max(c.high for c in candles),
            low=min(c.low for c in candles),
            close=candles[-1].close,
            volume=sum(c.volume for c in candles),
            trade_count=sum(c.trade_count for c in candles)
        )
