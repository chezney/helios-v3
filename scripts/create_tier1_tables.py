"""
Create Tier 1 Database Tables - PRD Compliant Schema

Creates all Tier 1 tables according to PRD specification:
- market_ohlc: Multi-timeframe OHLC candles
- engineered_features: 90-feature vectors in JSONB format
- orderbook_snapshots: Order book depth data
- market_trades: Individual trade records

Phase 1, Week 1-2: Complete database schema setup.
"""

import asyncio
import asyncpg

from config.settings import settings
from src.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__, component="database_setup")


async def main():
    """Create Tier 1 tables with PRD-compliant schema"""
    print("=" * 80)
    print("  HELIOS V3.0 - CREATE TIER 1 DATABASE TABLES")
    print("  Phase 1, Week 1-2: Database schema setup (PRD Compliant)")
    print("=" * 80)
    print()

    # Connect to database
    logger.info("Connecting to PostgreSQL...")
    try:
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            database=settings.database.postgres_db,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password
        )
        logger.info("[OK] Database connection established")
    except Exception as e:
        logger.error(f"[FAIL] Database connection failed: {e}")
        print(f"\n[FAIL] Database connection failed: {e}")
        return

    # Create tables
    print()
    print("Creating Tier 1 tables (PRD specification)...")
    print()

    try:
        # ============================================================
        # TABLE 1: market_ohlc - Multi-timeframe OHLC candles
        # ============================================================
        print("  Creating table: market_ohlc...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_ohlc (
                id BIGSERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,  -- '1m', '5m', '15m', '1h', '1d'
                open_price DECIMAL(20, 8) NOT NULL,
                high_price DECIMAL(20, 8) NOT NULL,
                low_price DECIMAL(20, 8) NOT NULL,
                close_price DECIMAL(20, 8) NOT NULL,
                volume DECIMAL(20, 8) NOT NULL,
                quote_volume DECIMAL(20, 8),
                num_trades INTEGER,
                open_time TIMESTAMP NOT NULL,
                close_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(pair, timeframe, open_time)
            )
        """)
        print("    [OK] market_ohlc created")

        # Indexes for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ohlc_pair_timeframe_close
            ON market_ohlc(pair, timeframe, close_time DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ohlc_close_time
            ON market_ohlc(close_time DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ohlc_pair_tf_open
            ON market_ohlc(pair, timeframe, open_time DESC)
        """)
        print("    [OK] Indexes created")

        # ============================================================
        # TABLE 2: engineered_features - ML feature vectors
        # ============================================================
        print("  Creating table: engineered_features...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS engineered_features (
                id BIGSERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,

                -- Complete 90-feature vector as JSON for flexibility
                -- Format: {"features": [f1, f2, ..., f90], "feature_names": ["1m_return", ...]}
                features_vector JSONB NOT NULL,

                computed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("    [OK] engineered_features created")

        # Index for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_features_pair_computed
            ON engineered_features(pair, computed_at DESC)
        """)
        print("    [OK] Index created")

        # ============================================================
        # TABLE 3: orderbook_snapshots - Order book depth data
        # ============================================================
        print("  Creating table: orderbook_snapshots...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                id BIGSERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                bids JSONB NOT NULL,  -- [{"price": float, "quantity": float}, ...]
                asks JSONB NOT NULL,
                bid_ask_spread DECIMAL(10, 6),
                market_depth_10 DECIMAL(20, 8),  -- Total volume in top 10 levels
                snapshot_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("    [OK] orderbook_snapshots created")

        # Index for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orderbook_pair_time
            ON orderbook_snapshots(pair, snapshot_time DESC)
        """)
        print("    [OK] Index created")

        # ============================================================
        # TABLE 4: market_trades - Individual trade records
        # ============================================================
        print("  Creating table: market_trades...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_trades (
                id BIGSERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                price DECIMAL(20, 8) NOT NULL,
                quantity DECIMAL(20, 8) NOT NULL,
                side VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
                trade_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("    [OK] market_trades created")

        # Index for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_pair_time
            ON market_trades(pair, trade_time DESC)
        """)
        print("    [OK] Index created")

        # ============================================================
        # Verify tables exist
        # ============================================================
        print()
        print("Verifying tables...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('market_ohlc', 'engineered_features', 'orderbook_snapshots', 'market_trades')
            ORDER BY table_name
        """)

        for table in tables:
            row_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
            print(f"  [OK] {table['table_name']:<30} ({row_count:,} rows)")

        print()
        print("=" * 80)
        print("  [SUCCESS] TIER 1 TABLES CREATED SUCCESSFULLY")
        print("=" * 80)
        print()
        print("  Tables created (PRD Specification):")
        print("    - market_ohlc          (OHLC candles, multi-timeframe)")
        print("    - engineered_features  (90-feature vectors in JSONB)")
        print("    - orderbook_snapshots  (Order book depth data)")
        print("    - market_trades        (Individual trade records)")
        print()

    except Exception as e:
        logger.error(f"Failed to create tables: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to create tables: {e}")
        return
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
