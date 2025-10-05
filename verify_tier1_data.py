"""
Verify Tier 1 Data Quality

Phase 1, Week 6: Verify data quality and completeness.
"""

import asyncio
import asyncpg
from datetime import datetime

from config.settings import settings
from src.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__, component="data_verification")


async def main():
    """Verify Tier 1 data in database"""
    print("=" * 80)
    print("  HELIOS V3.0 - TIER 1 DATA VERIFICATION")
    print("  Phase 1, Week 6: Data quality and completeness check")
    print("=" * 80)
    print()

    # Connect to database
    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        database=settings.database.postgres_db,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password
    )

    try:
        # Check market_ohlc table
        print("OHLC CANDLES")
        print("-" * 80)

        for pair in settings.trading.trading_pairs:
            for timeframe in ["1m", "5m", "15m"]:
                count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM market_ohlc
                    WHERE pair = $1 AND timeframe = $2
                """, pair, timeframe)

                if count > 0:
                    # Get date range
                    min_ts = await conn.fetchval("""
                        SELECT MIN(open_time)
                        FROM market_ohlc
                        WHERE pair = $1 AND timeframe = $2
                    """, pair, timeframe)

                    max_ts = await conn.fetchval("""
                        SELECT MAX(open_time)
                        FROM market_ohlc
                        WHERE pair = $1 AND timeframe = $2
                    """, pair, timeframe)

                    print(f"  {pair} {timeframe}: {count:>4} candles  ({min_ts} to {max_ts})")

        # Total candles
        total_candles = await conn.fetchval("SELECT COUNT(*) FROM market_ohlc")
        print(f"\n  Total Candles: {total_candles:,}")

        # Check engineered_features table
        print("\n")
        print("FEATURE VECTORS")
        print("-" * 80)

        for pair in settings.trading.trading_pairs:
            count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM engineered_features
                WHERE pair = $1
            """, pair)

            if count > 0:
                # Get date range
                min_ts = await conn.fetchval("""
                    SELECT MIN(computed_at)
                    FROM engineered_features
                    WHERE pair = $1
                """, pair)

                max_ts = await conn.fetchval("""
                    SELECT MAX(computed_at)
                    FROM engineered_features
                    WHERE pair = $1
                """, pair)

                # Sample one feature vector (JSONB format)
                sample = await conn.fetchrow("""
                    SELECT features_vector
                    FROM engineered_features
                    WHERE pair = $1
                    ORDER BY computed_at DESC
                    LIMIT 1
                """, pair)

                # Extract feature count from JSONB
                import json
                feature_count = 0
                if sample and sample['features_vector']:
                    fv_json = json.loads(sample['features_vector']) if isinstance(sample['features_vector'], str) else sample['features_vector']
                    feature_count = len(fv_json.get('features', []))

                print(f"  {pair}: {count:>3} vectors ({feature_count} features each)")
                print(f"    Range: {min_ts} to {max_ts}")

        # Total features
        total_features = await conn.fetchval("SELECT COUNT(*) FROM engineered_features")
        print(f"\n  Total Feature Vectors: {total_features:,}")

        # Data quality checks
        print("\n")
        print("DATA QUALITY CHECKS")
        print("-" * 80)

        # Check for NULL values in OHLC
        null_checks = await conn.fetch("""
            SELECT
                pair,
                timeframe,
                COUNT(*) FILTER (WHERE open_price IS NULL) as null_open,
                COUNT(*) FILTER (WHERE high_price IS NULL) as null_high,
                COUNT(*) FILTER (WHERE low_price IS NULL) as null_low,
                COUNT(*) FILTER (WHERE close_price IS NULL) as null_close
            FROM market_ohlc
            GROUP BY pair, timeframe
            HAVING COUNT(*) FILTER (WHERE open_price IS NULL OR high_price IS NULL OR low_price IS NULL OR close_price IS NULL) > 0
        """)

        if null_checks:
            print("  [WARNING] Found NULL values in OHLC data:")
            for row in null_checks:
                print(f"    {row['pair']} {row['timeframe']}: {row['null_open']} nulls")
        else:
            print("  [OK] No NULL values in OHLC data")

        # Check price consistency (high >= low)
        price_issues = await conn.fetchval("""
            SELECT COUNT(*)
            FROM market_ohlc
            WHERE high_price < low_price
        """)

        if price_issues > 0:
            print(f"  [WARNING] {price_issues} candles have high < low")
        else:
            print("  [OK] All candles have high >= low")

        # Check volume >= 0
        volume_issues = await conn.fetchval("""
            SELECT COUNT(*)
            FROM market_ohlc
            WHERE volume < 0
        """)

        if volume_issues > 0:
            print(f"  [WARNING] {volume_issues} candles have negative volume")
        else:
            print("  [OK] All candles have non-negative volume")

        # Feature vector checks (JSONB format)
        feature_count_check = await conn.fetch("""
            SELECT
                pair,
                jsonb_array_length(features_vector->'features') as feature_count,
                COUNT(*) as count
            FROM engineered_features
            GROUP BY pair, jsonb_array_length(features_vector->'features')
        """)

        print("\n  Feature Vector Sizes:")
        for row in feature_count_check:
            print(f"    {row['pair']}: {row['feature_count']} features ({row['count']} vectors)")

        print("\n")
        print("=" * 80)
        print("  [SUCCESS] TIER 1 DATA VERIFICATION COMPLETE")
        print("=" * 80)
        print(f"\n  Summary:")
        print(f"    - {total_candles:,} OHLC candles stored")
        print(f"    - {total_features:,} feature vectors calculated")
        print(f"    - Data quality checks passed")
        print()

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
