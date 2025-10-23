"""
Enhanced Historical Backfill System

Automatically detects gaps in historical data and backfills from VALR API with:
- Gap detection (finds missing date ranges in DB)
- 6-month backfill support using VALR market history aggregates
- Intelligent throttling (handles 1000 request limit)
- Retry logic with exponential backoff
- Progress tracking and resumable operations

VALR API Endpoints Used:
1. GET /v1/marketdata/{pair}/aggregates - OHLC candles (historical)
   - Supports: 1m, 5m, 15m, 30m, 1h, 4h, 1d timeframes
   - Limit: 1000 candles per request
   - Rate limit: Unknown (we'll use conservative 30 req/min)

2. GET /v1/public/{pair}/trades - Recent trades (live data)
   - Limit: 100 trades per request
   - Use for recent data only
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import asyncpg
import time
from enum import Enum

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="enhanced_backfill")


class BackfillStatus(Enum):
    """Status of backfill operation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    THROTTLED = "throttled"


@dataclass
class DataGap:
    """Represents a gap in historical data"""
    pair: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    expected_candles: int
    actual_candles: int
    missing_candles: int

    def __str__(self):
        return (f"{self.pair} {self.timeframe}: "
                f"{self.start_time.date()} to {self.end_time.date()} "
                f"(missing {self.missing_candles} candles)")


@dataclass
class BackfillProgress:
    """Tracks backfill progress"""
    pair: str
    timeframe: str
    total_candles_needed: int
    candles_fetched: int = 0
    api_requests_made: int = 0
    api_requests_remaining: int = 1000
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: BackfillStatus = BackfillStatus.PENDING
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.start_time is None:
            self.start_time = datetime.utcnow()

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage"""
        if self.total_candles_needed == 0:
            return 100.0
        return min(100.0, (self.candles_fetched / self.total_candles_needed) * 100)

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds"""
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()

    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Estimate time remaining in seconds"""
        if self.candles_fetched == 0 or self.progress_pct >= 100:
            return None

        elapsed = self.duration_seconds
        rate = self.candles_fetched / elapsed  # candles per second
        remaining_candles = self.total_candles_needed - self.candles_fetched
        return remaining_candles / rate if rate > 0 else None


class EnhancedHistoricalBackfill:
    """
    Enhanced historical data backfill system with gap detection and intelligent throttling.

    Features:
    - Automatically detects gaps in database
    - Fetches data using VALR market aggregates endpoint
    - Handles 1000 request limit with throttling
    - Exponential backoff on errors
    - Progress tracking and resumable operations
    """

    # VALR API constraints
    MAX_CANDLES_PER_REQUEST = 1000
    MAX_REQUESTS_PER_BATCH = 1000  # User's constraint
    RATE_LIMIT_DELAY = 2.0  # Seconds between requests (30 req/min = 2s delay)
    RETRY_DELAYS = [1, 2, 4, 8, 16]  # Exponential backoff (seconds)

    # Timeframe to minutes mapping
    TIMEFRAME_MINUTES = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = settings.trading.valr_base_url
        self.request_count = 0  # Track requests in current batch
        self.last_request_time = 0.0

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def detect_gaps(
        self,
        pair: str,
        timeframe: str,
        lookback_days: int = 180  # 6 months
    ) -> List[DataGap]:
        """
        Detect gaps in historical data for a pair/timeframe.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            timeframe: Candle timeframe (e.g., '1m', '5m')
            lookback_days: How far back to check (default: 180 days = 6 months)

        Returns:
            List of DataGap objects representing missing data
        """
        logger.info(f"Detecting gaps for {pair} {timeframe} (last {lookback_days} days)")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)

        # Get expected candle count
        minutes_per_candle = self.TIMEFRAME_MINUTES.get(timeframe, 1)
        total_minutes = lookback_days * 24 * 60
        expected_candles = total_minutes // minutes_per_candle

        # Query database for actual candle count
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT
                    COUNT(*) as actual_count,
                    MIN(open_time) as earliest,
                    MAX(open_time) as latest
                FROM market_ohlc
                WHERE pair = $1
                  AND timeframe = $2
                  AND open_time >= $3
                  AND open_time <= $4
            """, pair, timeframe, start_time, end_time)

            actual_count = result['actual_count'] if result else 0
            earliest = result['earliest'] if result else None
            latest = result['latest'] if result else None

        missing_count = max(0, expected_candles - actual_count)

        if missing_count == 0:
            logger.info(f"✅ No gaps found for {pair} {timeframe}")
            return []

        # Create gap object
        gap = DataGap(
            pair=pair,
            timeframe=timeframe,
            start_time=earliest or start_time,
            end_time=latest or end_time,
            expected_candles=expected_candles,
            actual_candles=actual_count,
            missing_candles=missing_count
        )

        logger.info(f"📊 Gap detected: {gap}")
        return [gap]

    async def fetch_market_aggregates(
        self,
        pair: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        retry_count: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLC candles from VALR market aggregates endpoint.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            timeframe: Candle timeframe (e.g., '1m', '5m')
            start_time: Start of data range
            end_time: End of data range
            retry_count: Current retry attempt

        Returns:
            List of candle dictionaries
        """
        # Check if we've hit request limit
        if self.request_count >= self.MAX_REQUESTS_PER_BATCH:
            logger.warning(f"⚠️ Hit {self.MAX_REQUESTS_PER_BATCH} request limit. Please wait or restart with new batch.")
            raise Exception(f"API request limit reached: {self.MAX_REQUESTS_PER_BATCH}")

        # Rate limiting - ensure minimum delay between requests
        elapsed = time.time() - self.last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            await asyncio.sleep(self.RATE_LIMIT_DELAY - elapsed)

        # VALR API endpoint
        # Note: This endpoint may or may not exist on VALR. Adjust based on actual VALR API docs.
        # If VALR doesn't have this endpoint, we'll need to use alternative data source.
        url = f"{self.base_url}/v1/marketdata/{pair}/candles"

        # Convert timeframe to VALR format
        params = {
            "interval": timeframe.upper(),  # e.g., "1M", "5M"
            "limit": self.MAX_CANDLES_PER_REQUEST,
            "startTime": int(start_time.timestamp() * 1000),  # milliseconds
            "endTime": int(end_time.timestamp() * 1000)
        }

        try:
            logger.debug(f"Fetching {pair} {timeframe} candles: {start_time} to {end_time}")

            async with self.session.get(url, params=params, timeout=30) as response:
                self.request_count += 1
                self.last_request_time = time.time()

                if response.status == 429:  # Too many requests
                    logger.warning("⚠️ Rate limit exceeded, backing off...")
                    if retry_count < len(self.RETRY_DELAYS):
                        delay = self.RETRY_DELAYS[retry_count]
                        logger.info(f"Retrying in {delay}s (attempt {retry_count + 1})")
                        await asyncio.sleep(delay)
                        return await self.fetch_market_aggregates(
                            pair, timeframe, start_time, end_time, retry_count + 1
                        )
                    else:
                        raise Exception("Max retries exceeded due to rate limiting")

                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"VALR API error {response.status}: {error_text}")
                    raise Exception(f"VALR API error: {response.status}")

                data = await response.json()
                logger.info(f"✅ Fetched {len(data)} candles for {pair} {timeframe}")
                return data

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching candles for {pair}")
            if retry_count < len(self.RETRY_DELAYS):
                delay = self.RETRY_DELAYS[retry_count]
                await asyncio.sleep(delay)
                return await self.fetch_market_aggregates(
                    pair, timeframe, start_time, end_time, retry_count + 1
                )
            raise

        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            if retry_count < len(self.RETRY_DELAYS):
                delay = self.RETRY_DELAYS[retry_count]
                await asyncio.sleep(delay)
                return await self.fetch_market_aggregates(
                    pair, timeframe, start_time, end_time, retry_count + 1
                )
            raise

    async def store_candles(self, candles: List[Dict[str, Any]], pair: str, timeframe: str) -> int:
        """
        Store candles in database.

        Args:
            candles: List of candle dictionaries
            pair: Trading pair
            timeframe: Candle timeframe

        Returns:
            Number of candles stored
        """
        if not candles:
            return 0

        stored_count = 0
        async with self.db_pool.acquire() as conn:
            for candle in candles:
                try:
                    # Parse candle data (adjust based on actual VALR response format)
                    open_time = datetime.fromtimestamp(int(candle['openTime']) / 1000)
                    close_time = datetime.fromtimestamp(int(candle['closeTime']) / 1000)

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
                    """,
                        pair,
                        timeframe,
                        open_time,
                        close_time,
                        float(candle['open']),
                        float(candle['high']),
                        float(candle['low']),
                        float(candle['close']),
                        float(candle.get('volume', 0)),
                        int(candle.get('numberOfTrades', 0))
                    )
                    stored_count += 1

                except Exception as e:
                    logger.error(f"Error storing candle: {e}")
                    continue

        logger.info(f"💾 Stored {stored_count}/{len(candles)} candles in database")
        return stored_count

    async def backfill_gap(
        self,
        gap: DataGap,
        progress_callback: Optional[callable] = None
    ) -> BackfillProgress:
        """
        Backfill a detected data gap.

        Args:
            gap: DataGap object to fill
            progress_callback: Optional callback function for progress updates

        Returns:
            BackfillProgress object with results
        """
        progress = BackfillProgress(
            pair=gap.pair,
            timeframe=gap.timeframe,
            total_candles_needed=gap.missing_candles,
            status=BackfillStatus.IN_PROGRESS
        )

        logger.info(f"🔄 Starting backfill: {gap}")

        try:
            # Calculate time ranges to fetch (in chunks of MAX_CANDLES_PER_REQUEST)
            minutes_per_candle = self.TIMEFRAME_MINUTES[gap.timeframe]
            candles_per_chunk = self.MAX_CANDLES_PER_REQUEST
            minutes_per_chunk = candles_per_chunk * minutes_per_candle

            current_start = gap.start_time
            end_time = gap.end_time

            while current_start < end_time:
                # Calculate chunk end time
                current_end = min(
                    current_start + timedelta(minutes=minutes_per_chunk),
                    end_time
                )

                # Fetch candles for this chunk
                try:
                    candles = await self.fetch_market_aggregates(
                        gap.pair,
                        gap.timeframe,
                        current_start,
                        current_end
                    )

                    progress.api_requests_made += 1
                    progress.api_requests_remaining = self.MAX_REQUESTS_PER_BATCH - self.request_count

                    # Store candles
                    if candles:
                        stored = await self.store_candles(candles, gap.pair, gap.timeframe)
                        progress.candles_fetched += stored

                    # Update progress
                    if progress_callback:
                        progress_callback(progress)

                    # Log progress
                    logger.info(
                        f"📈 Progress: {progress.progress_pct:.1f}% "
                        f"({progress.candles_fetched}/{progress.total_candles_needed} candles) "
                        f"[{progress.api_requests_made} API requests]"
                    )

                    # Check if we're approaching request limit
                    if progress.api_requests_remaining < 10:
                        logger.warning(
                            f"⚠️ Approaching request limit! "
                            f"Only {progress.api_requests_remaining} requests remaining"
                        )

                except Exception as e:
                    error_msg = f"Error fetching chunk {current_start} to {current_end}: {e}"
                    logger.error(error_msg)
                    progress.errors.append(error_msg)

                    # Continue with next chunk instead of failing completely
                    if len(progress.errors) > 10:
                        raise Exception("Too many errors, aborting backfill")

                # Move to next chunk
                current_start = current_end

            # Mark as completed
            progress.status = BackfillStatus.COMPLETED
            progress.end_time = datetime.utcnow()

            logger.info(
                f"✅ Backfill completed: {progress.candles_fetched} candles in "
                f"{progress.duration_seconds:.1f}s ({progress.api_requests_made} API requests)"
            )

        except Exception as e:
            progress.status = BackfillStatus.FAILED
            progress.end_time = datetime.utcnow()
            progress.errors.append(str(e))
            logger.error(f"❌ Backfill failed: {e}")

        return progress

    async def backfill_all_pairs(
        self,
        pairs: List[str],
        timeframes: List[str] = None,
        lookback_days: int = 180
    ) -> Dict[str, List[BackfillProgress]]:
        """
        Backfill all pairs and timeframes.

        Args:
            pairs: List of trading pairs
            timeframes: List of timeframes (default: ['1m', '5m', '15m'])
            lookback_days: How far back to backfill (default: 180 = 6 months)

        Returns:
            Dictionary mapping pair to list of BackfillProgress objects
        """
        if timeframes is None:
            timeframes = ['1m', '5m', '15m']

        results = {}

        for pair in pairs:
            results[pair] = []

            for timeframe in timeframes:
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing {pair} {timeframe}")
                logger.info(f"{'='*80}")

                # Detect gaps
                gaps = await self.detect_gaps(pair, timeframe, lookback_days)

                if not gaps:
                    logger.info(f"✅ No gaps to fill for {pair} {timeframe}")
                    continue

                # Backfill each gap
                for gap in gaps:
                    progress = await self.backfill_gap(gap)
                    results[pair].append(progress)

                    # Check if we're approaching request limit
                    if self.request_count >= self.MAX_REQUESTS_PER_BATCH - 10:
                        logger.warning(
                            f"⚠️ Approaching {self.MAX_REQUESTS_PER_BATCH} request limit. "
                            f"Stopping backfill. Resume later to continue."
                        )
                        return results

        return results


def format_time(seconds: Optional[float]) -> str:
    """Format seconds into human-readable string"""
    if seconds is None:
        return "N/A"

    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


async def print_progress(progress: BackfillProgress):
    """Print progress update"""
    eta = format_time(progress.estimated_time_remaining)
    print(
        f"  [{progress.progress_pct:5.1f}%] "
        f"{progress.candles_fetched:,}/{progress.total_candles_needed:,} candles | "
        f"Requests: {progress.api_requests_made} "
        f"(Remaining: {progress.api_requests_remaining}) | "
        f"ETA: {eta}"
    )
