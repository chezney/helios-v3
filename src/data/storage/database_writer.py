"""
Helios Trading System V3.0 - Database Writer
Persists market data, candles, and features to PostgreSQL
Following PRD Section 7: Data Storage
"""

import asyncpg
from typing import Optional
from datetime import datetime, timezone

from config.settings import settings
from src.utils.logger import get_logger
from src.data.processors import OHLC, FeatureVector
from src.data.collectors import MarketTick, OrderBookSnapshot

logger = get_logger(__name__, component="tier1_storage")


class DatabaseWriter:
    """
    Writes Tier 1 data to PostgreSQL database.

    Handles:
    - OHLC candles (market_ohlc table)
    - Orderbook snapshots (orderbook_snapshots table)
    - Trade ticks (market_trades table)
    - Feature vectors (engineered_features table)
    """

    def __init__(self, connection_pool: Optional[asyncpg.Pool] = None):
        """
        Initialize database writer.

        Args:
            connection_pool: Optional existing connection pool. If None, creates new one.
        """
        self.pool = connection_pool
        self._own_pool = connection_pool is None

    async def initialize(self):
        """Initialize database connection pool"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    host=settings.database.postgres_host,
                    port=settings.database.postgres_port,
                    user=settings.database.postgres_user,
                    password=settings.database.postgres_password,
                    database=settings.database.postgres_db,
                    min_size=2,
                    max_size=10
                )
                logger.info(f"Database connection pool created (size: 2-10)")
            except Exception as e:
                logger.error(f"Failed to create database pool: {e}", exc_info=True)
                raise

    async def close(self):
        """Close database connection pool"""
        if self.pool and self._own_pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def save_candle(self, ohlc: OHLC) -> bool:
        """
        Save OHLC candle to market_ohlc table.

        Args:
            ohlc: OHLC candle data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to naive UTC datetime (PostgreSQL expects naive UTC)
            timestamp = ohlc.timestamp
            if timestamp.tzinfo is not None:
                # Timezone-aware - convert to UTC and remove timezone
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO market_ohlc
                    (pair, timeframe, open_time, close_time, open_price, high_price,
                     low_price, close_price, volume, num_trades)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (pair, timeframe, open_time)
                    DO UPDATE SET
                        close_price = EXCLUDED.close_price,
                        high_price = GREATEST(market_ohlc.high_price, EXCLUDED.high_price),
                        low_price = LEAST(market_ohlc.low_price, EXCLUDED.low_price),
                        volume = market_ohlc.volume + EXCLUDED.volume,
                        num_trades = market_ohlc.num_trades + EXCLUDED.num_trades
                    """,
                    ohlc.pair,
                    ohlc.timeframe,
                    timestamp,
                    timestamp,  # close_time same as open for now
                    ohlc.open,
                    ohlc.high,
                    ohlc.low,
                    ohlc.close,
                    ohlc.volume,
                    ohlc.trade_count
                )

            logger.debug(
                f"Saved candle: {ohlc.pair} {ohlc.timeframe} @ {ohlc.timestamp.strftime('%H:%M:%S')} "
                f"O:{ohlc.open:.2f} H:{ohlc.high:.2f} L:{ohlc.low:.2f} C:{ohlc.close:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save candle: {e}", exc_info=True)
            return False

    async def save_orderbook(self, snapshot: OrderBookSnapshot) -> bool:
        """
        Save orderbook snapshot to orderbook_snapshots table.

        Args:
            snapshot: Orderbook snapshot data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to naive UTC datetime
            timestamp = snapshot.timestamp
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            # Calculate metrics
            bid_ask_spread = 0.0
            orderbook_imbalance = 0.5
            market_depth_10 = 0.0

            if snapshot.bids and snapshot.asks:
                best_bid = snapshot.bids[0]['price']
                best_ask = snapshot.asks[0]['price']
                bid_ask_spread = best_ask - best_bid

                # Calculate orderbook imbalance (bid volume / total volume)
                bid_volume = sum(b['quantity'] for b in snapshot.bids[:10])
                ask_volume = sum(a['quantity'] for a in snapshot.asks[:10])
                total_volume = bid_volume + ask_volume
                if total_volume > 0:
                    orderbook_imbalance = bid_volume / total_volume

                # Market depth (total volume in top 10 levels)
                market_depth_10 = total_volume

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO orderbook_snapshots
                    (pair, snapshot_time, bids, asks, bid_ask_spread,
                     market_depth_10, orderbook_imbalance)
                    VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7)
                    """,
                    snapshot.pair,
                    timestamp,
                    str(snapshot.bids),  # Convert to JSON string
                    str(snapshot.asks),
                    bid_ask_spread,
                    market_depth_10,
                    orderbook_imbalance
                )

            logger.debug(f"Saved orderbook: {snapshot.pair} @ {snapshot.timestamp.strftime('%H:%M:%S')}")
            return True

        except Exception as e:
            logger.error(f"Failed to save orderbook: {e}", exc_info=True)
            return False

    async def save_trade(self, tick: MarketTick) -> bool:
        """
        Save trade tick to market_trades table.

        Args:
            tick: Market tick data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to naive UTC datetime
            timestamp = tick.timestamp
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO market_trades
                    (pair, side, price, quantity, executed_at)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    tick.pair,
                    tick.side,
                    tick.price,
                    tick.quantity,
                    timestamp
                )

            logger.debug(
                f"Saved trade: {tick.pair} {tick.side} {tick.quantity:.8f} @ R{tick.price:,.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save trade: {e}", exc_info=True)
            return False

    async def save_features(self, features: FeatureVector) -> bool:
        """
        Save feature vector to engineered_features table.

        Args:
            features: Feature vector with 90 features

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to naive UTC datetime
            timestamp = features.timestamp
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            # Split features into timeframes (30 each)
            hfp_features = features.features[0:30].tolist()   # 1min
            mfp_features = features.features[30:60].tolist()  # 5min
            lfp_features = features.features[60:90].tolist()  # 15min

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO engineered_features
                    (pair, timestamp, hfp_features, mfp_features, lfp_features)
                    VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb)
                    ON CONFLICT (pair, timestamp)
                    DO UPDATE SET
                        hfp_features = EXCLUDED.hfp_features,
                        mfp_features = EXCLUDED.mfp_features,
                        lfp_features = EXCLUDED.lfp_features
                    """,
                    features.pair,
                    timestamp,
                    str(hfp_features),
                    str(mfp_features),
                    str(lfp_features)
                )

            logger.debug(
                f"Saved features: {features.pair} @ {features.timestamp.strftime('%H:%M:%S')} "
                f"(90 features)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save features: {e}", exc_info=True)
            return False

    async def get_recent_candles(
        self,
        pair: str,
        timeframe: str,
        limit: int = 100
    ) -> list:
        """
        Fetch recent candles from database.

        Args:
            pair: Trading pair
            timeframe: Timeframe (1m, 5m, 15m)
            limit: Number of candles to fetch

        Returns:
            List of candle records
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT pair, timeframe, open_time, open_price, high_price,
                           low_price, close_price, volume, num_trades
                    FROM market_ohlc
                    WHERE pair = $1 AND timeframe = $2
                    ORDER BY open_time DESC
                    LIMIT $3
                    """,
                    pair,
                    timeframe,
                    limit
                )

            # Convert to list of dicts
            candles = [dict(row) for row in rows]
            candles.reverse()  # Oldest first

            logger.debug(f"Fetched {len(candles)} candles: {pair} {timeframe}")
            return candles

        except Exception as e:
            logger.error(f"Failed to fetch candles: {e}", exc_info=True)
            return []

    async def get_stats(self) -> dict:
        """Get database statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Count records in each table
                candle_count = await conn.fetchval("SELECT COUNT(*) FROM market_ohlc")
                trade_count = await conn.fetchval("SELECT COUNT(*) FROM market_trades")
                orderbook_count = await conn.fetchval("SELECT COUNT(*) FROM orderbook_snapshots")
                feature_count = await conn.fetchval("SELECT COUNT(*) FROM engineered_features")

            return {
                "candles": candle_count,
                "trades": trade_count,
                "orderbooks": orderbook_count,
                "features": feature_count
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}", exc_info=True)
            return {
                "candles": 0,
                "trades": 0,
                "orderbooks": 0,
                "features": 0
            }
