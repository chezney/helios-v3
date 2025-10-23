"""
VALR Candle Poller - Continuous REST API Polling Service

Polls VALR REST API every 60 seconds to fetch pre-aggregated 1-minute candles.
Replaces LiveCandleGenerator which relied on WebSocket NEW_TRADE events
(which are account-only, not public market data).

Architecture:
- Polls /v1/public/{pair}/buckets endpoint every 60 seconds
- Fetches last 2 candles per pair (current + previous to avoid gaps)
- Duplicate detection using last_candle_timestamp tracking
- Rate limiting with exponential backoff
- Event emission to Autonomous Engine on new candles
- Stores directly to market_ohlc database table

Author: Helios V3.0 Team
Date: October 2025
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from decimal import Decimal
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__, component="valr_candle_poller")


class VALRCandlePoller:
    """
    Continuous REST API polling service for VALR 1-minute candles.

    Fetches pre-aggregated candles from VALR's /buckets endpoint every 60 seconds,
    stores them in the database, and emits NEW_CANDLE events to trigger
    downstream processing (features, predictions, trading).

    Attributes:
        pairs (List[str]): Trading pairs to poll (e.g., ["BTCZAR", "ETHZAR", "SOLZAR"])
        db: Database connection for storing candles
        event_queue: Optional asyncio queue for emitting NEW_CANDLE events
        running (bool): Polling loop control flag
        last_candle_times (Dict[str, datetime]): Duplicate detection per pair
        consecutive_errors (Dict[str, int]): Error tracking per pair for backoff
        base_url (str): VALR API base URL
    """

    def __init__(
        self,
        db,
        pairs: List[str] = None,
        event_queue: Optional[asyncio.Queue] = None,
        base_url: str = "https://api.valr.com"
    ):
        """
        Initialize VALR Candle Poller.

        Args:
            db: Database connection (asyncpg connection or SQLAlchemy session)
            pairs: List of trading pairs to poll (defaults to ["BTCZAR", "ETHZAR", "SOLZAR"])
            event_queue: Optional queue for emitting NEW_CANDLE events to Autonomous Engine
            base_url: VALR API base URL (default: https://api.valr.com)
        """
        self.db = db
        self.pairs = pairs or ["BTCZAR", "ETHZAR", "SOLZAR"]
        self.event_queue = event_queue
        self.base_url = base_url

        # Control flags
        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None

        # Duplicate detection: track last candle timestamp per pair
        self.last_candle_times: Dict[str, datetime] = {}

        # Error tracking for exponential backoff
        self.consecutive_errors: Dict[str, int] = {}
        self.backoff_delays: Dict[str, float] = {}

        # Rate limiting
        self.last_request_time: float = 0.0
        self.min_request_interval: float = 1.0  # Minimum 1 second between requests

        logger.info(f"VALRCandlePoller initialized for pairs: {self.pairs}")

    async def start(self):
        """
        Start continuous polling loop.

        Polls VALR REST API every 60 seconds for pre-aggregated 1-minute candles.
        Runs indefinitely until stop() is called.
        """
        if self.running:
            logger.warning("Poller already running, ignoring start request")
            return

        self.running = True
        logger.info("Starting VALRCandlePoller - polling every 60 seconds")

        # Create aiohttp session
        self.session = aiohttp.ClientSession()

        try:
            while self.running:
                # Poll all pairs
                for pair in self.pairs:
                    if not self.running:
                        break

                    try:
                        await self._poll_pair(pair)
                    except Exception as e:
                        logger.error(f"Error polling {pair}: {e}", exc_info=True)
                        await self._handle_error(pair, e)

                # Wait 60 seconds before next poll
                if self.running:
                    logger.debug("Sleeping 60 seconds until next poll cycle")
                    await asyncio.sleep(60)

        finally:
            # Cleanup
            if self.session:
                await self.session.close()
            logger.info("VALRCandlePoller stopped")

    async def stop(self):
        """Stop the polling loop gracefully."""
        logger.info("Stopping VALRCandlePoller...")
        self.running = False

    async def _poll_pair(self, pair: str):
        """
        Poll VALR API for latest candles for a single pair.

        Fetches last 2 candles (current + previous) to avoid missing any.
        Processes each candle and stores if not duplicate.

        Args:
            pair: Trading pair (e.g., "BTCZAR")
        """
        # Rate limiting
        await self._rate_limit()

        # Fetch candles from VALR
        candles = await self._fetch_candles_from_api(pair)

        if not candles:
            logger.warning(f"No candles received for {pair}")
            return

        # Process each candle
        new_candles_count = 0
        for candle in candles:
            if await self._process_candle(pair, candle):
                new_candles_count += 1

        if new_candles_count > 0:
            logger.info(f"Stored {new_candles_count} new candle(s) for {pair}")

            # Reset error tracking on success
            self.consecutive_errors[pair] = 0
            self.backoff_delays[pair] = 0.0

    async def _fetch_candles_from_api(self, pair: str) -> List[Dict]:
        """
        Fetch candles from VALR /buckets REST API endpoint.

        API Endpoint: GET /v1/public/{pair}/buckets
        Parameters:
            - periodSeconds: 60 (1-minute candles)
            - limit: 2 (fetch last 2 candles to avoid gaps)

        Args:
            pair: Trading pair (e.g., "BTCZAR")

        Returns:
            List of candle dictionaries from VALR API
        """
        url = f"{self.base_url}/v1/public/{pair}/buckets"
        params = {
            "periodSeconds": 60,  # 1-minute candles
            "limit": 2            # Fetch last 2 to ensure no gaps
        }

        try:
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    candles = await response.json()
                    logger.debug(f"Fetched {len(candles)} candles for {pair}")
                    return candles

                elif response.status == 429:
                    logger.warning(f"Rate limit hit for {pair} (HTTP 429)")
                    raise RateLimitError("VALR API rate limit exceeded")

                else:
                    error_text = await response.text()
                    logger.error(f"VALR API error {response.status} for {pair}: {error_text[:200]}")
                    raise APIError(f"VALR API returned status {response.status}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching candles for {pair}")
            raise APIError(f"Timeout fetching candles for {pair}")

        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error for {pair}: {e}")
            raise APIError(f"HTTP client error: {e}")

    async def _process_candle(self, pair: str, candle: Dict) -> bool:
        """
        Process and store a single candle if not duplicate.

        Args:
            pair: Trading pair
            candle: Candle dict from VALR API

        Returns:
            True if candle was stored (new), False if duplicate
        """
        # Parse candle timestamp
        candle_time = self._parse_candle_timestamp(candle)

        # Duplicate detection
        if pair in self.last_candle_times:
            if candle_time <= self.last_candle_times[pair]:
                logger.debug(f"Skipping duplicate candle for {pair} at {candle_time}")
                return False

        # Store candle in database
        await self._store_candle(pair, candle, candle_time)

        # Emit NEW_CANDLE event
        await self._emit_new_candle_event(pair, candle_time)

        # Update tracking
        self.last_candle_times[pair] = candle_time

        return True

    def _parse_candle_timestamp(self, candle: Dict) -> datetime:
        """
        Parse candle timestamp from VALR API response.

        VALR returns timestamps in ISO 8601 format with 'Z' suffix.
        We store as timezone-naive UTC in the database.

        Args:
            candle: Candle dict from VALR API

        Returns:
            Timezone-naive datetime
        """
        # VALR format: "2025-10-08T21:35:00Z"
        timestamp_str = candle.get("startTime")

        # Remove 'Z' and parse
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # Convert to naive (database expects timezone-naive UTC)
        timestamp_naive = timestamp.replace(tzinfo=None)

        return timestamp_naive

    async def _store_candle(self, pair: str, candle: Dict, open_time: datetime):
        """
        Store candle in market_ohlc database table.

        Uses ON CONFLICT DO NOTHING to handle any duplicates gracefully.

        Args:
            pair: Trading pair
            candle: Candle dict from VALR API
            open_time: Candle open time (timezone-naive)
        """
        close_time = open_time + timedelta(seconds=59)

        query = """
            INSERT INTO market_ohlc
            (pair, timeframe, open_time, close_time, open_price, high_price,
             low_price, close_price, volume, num_trades)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (pair, timeframe, open_time) DO NOTHING
        """

        await self.db.execute(
            query,
            pair,
            "1m",
            open_time,
            close_time,
            Decimal(candle["open"]),
            Decimal(candle["high"]),
            Decimal(candle["low"]),
            Decimal(candle["close"]),
            Decimal(candle["volume"]),
            0  # num_trades not provided by buckets endpoint
        )

    async def _emit_new_candle_event(self, pair: str, candle_time: datetime):
        """
        Emit NEW_CANDLE event to Autonomous Engine event queue.

        This triggers downstream processing:
        - Feature calculation
        - Neural network prediction
        - Trading signal generation

        Args:
            pair: Trading pair
            candle_time: Candle timestamp
        """
        if self.event_queue is None:
            return

        event = {
            "type": "NEW_CANDLE",
            "pair": pair,
            "timeframe": "1m",
            "timestamp": candle_time
        }

        try:
            await self.event_queue.put(event)
            logger.debug(f"Emitted NEW_CANDLE event for {pair} at {candle_time}")
        except Exception as e:
            logger.error(f"Error emitting NEW_CANDLE event: {e}")

    async def _rate_limit(self):
        """
        Enforce rate limiting between API requests.

        Ensures minimum 1 second between requests to avoid hitting
        VALR API rate limits.
        """
        import time

        now = time.time()
        elapsed = now - self.last_request_time

        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            await asyncio.sleep(wait_time)

        self.last_request_time = time.time()

    async def _handle_error(self, pair: str, error: Exception):
        """
        Handle API errors with exponential backoff.

        Tracks consecutive errors per pair and applies increasing delays
        to avoid hammering the API during outages.

        Args:
            pair: Trading pair that experienced error
            error: Exception that occurred
        """
        # Increment error counter
        self.consecutive_errors[pair] = self.consecutive_errors.get(pair, 0) + 1
        error_count = self.consecutive_errors[pair]

        # Calculate backoff delay: 5s, 10s, 20s, 40s, 60s (max)
        if isinstance(error, RateLimitError):
            backoff = 60.0  # Wait 60s on rate limit
        else:
            backoff = min(60.0, 5.0 * (2 ** (error_count - 1)))

        self.backoff_delays[pair] = backoff

        logger.warning(
            f"Error for {pair} (count: {error_count}): {error}. "
            f"Backing off {backoff:.1f}s"
        )

        # Alert if too many consecutive errors
        if error_count > 5:
            logger.error(
                f"Critical: {error_count} consecutive errors for {pair}. "
                "Check API connectivity or pair validity."
            )

        # Apply backoff
        await asyncio.sleep(backoff)

    def get_status(self) -> Dict:
        """
        Get current poller status for monitoring.

        Returns:
            Dict with status information
        """
        return {
            "running": self.running,
            "pairs": self.pairs,
            "last_candle_times": {
                pair: time.isoformat() if (time := self.last_candle_times.get(pair)) else None
                for pair in self.pairs
            },
            "consecutive_errors": self.consecutive_errors,
            "backoff_delays": self.backoff_delays
        }


class APIError(Exception):
    """Raised when VALR API returns an error."""
    pass


class RateLimitError(APIError):
    """Raised when VALR API rate limit is exceeded (HTTP 429)."""
    pass
