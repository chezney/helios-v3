"""
Historical Data Backfill Script

Phase 1, Week 5: Backfill 90 days of historical data for BTCZAR, ETHZAR, SOLZAR
"""

import asyncio
import asyncpg
from datetime import datetime

from config.settings import settings
from src.data.collectors.historical_collector import HistoricalDataCollector
from src.utils.logger import setup_logging, get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__, component="backfill_script")


async def main():
    """Run historical backfill for all trading pairs"""
    print("=" * 80)
    print("  HELIOS V3.0 - HISTORICAL DATA BACKFILL")
    print("  Phase 1, Week 5: Collecting 90 days of historical data")
    print("=" * 80)
    print(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Pairs: {settings.trading.trading_pairs}")
    print("=" * 80)
    print()

    # Connect to database
    logger.info("Connecting to PostgreSQL...")
    try:
        db_pool = await asyncpg.create_pool(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            database=settings.database.postgres_db,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            min_size=2,
            max_size=10
        )
        logger.info("[OK] Database connection established")
    except Exception as e:
        logger.error(f"[FAIL] Database connection failed: {e}")
        print(f"\n❌ Database connection failed: {e}")
        return

    # Initialize historical collector
    async with HistoricalDataCollector() as collector:
        all_results = []

        # Backfill each pair
        for pair in settings.trading.trading_pairs:
            print()
            print("=" * 80)
            print(f"  BACKFILLING: {pair}")
            print("=" * 80)

            result = await collector.backfill_historical_data(
                pair=pair,
                days=90,  # Request 90 days (actual data limited by VALR API)
                db_pool=db_pool
            )

            all_results.append(result)

            # Display result
            print()
            print(f"  Status: {result['status'].upper()}")
            print(f"  Trades Fetched: {result['trades_fetched']:,}")
            print(f"  Candles Created: {result['candles_created']:,}")
            print(f"  Features Calculated: {result['features_calculated']:,}")
            if 'duration_seconds' in result:
                print(f"  Duration: {result['duration_seconds']:.2f} seconds")
            if 'error' in result:
                print(f"  Error: {result['error']}")
            print("=" * 80)

            # Wait between pairs to avoid rate limiting
            await asyncio.sleep(5)

    # Close database pool
    await db_pool.close()

    # Summary
    print()
    print("=" * 80)
    print("  BACKFILL SUMMARY")
    print("=" * 80)

    total_trades = sum(r['trades_fetched'] for r in all_results)
    total_candles = sum(r['candles_created'] for r in all_results)
    total_features = sum(r['features_calculated'] for r in all_results)
    successful = sum(1 for r in all_results if r['status'] == 'completed')

    print(f"  Pairs Processed: {len(all_results)}")
    print(f"  Successful: {successful}/{len(all_results)}")
    print(f"  Total Trades: {total_trades:,}")
    print(f"  Total Candles: {total_candles:,}")
    print(f"  Total Features: {total_features:,}")
    print()

    if successful == len(all_results):
        print("  ✅ ALL BACKFILLS COMPLETED SUCCESSFULLY")
        print()
        print("  ⚠️  NOTE: Due to VALR API limitations, only recent trades are available.")
        print("      For true 90-day historical data, would need:")
        print("      1. VALR historical data API (if available)")
        print("      2. Alternative data provider (e.g., CryptoCompare, CoinGecko)")
        print("      3. Manual data collection over time")
    else:
        print("  ⚠️  SOME BACKFILLS FAILED - Check logs above")

    print("=" * 80)
    print(f"  End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
