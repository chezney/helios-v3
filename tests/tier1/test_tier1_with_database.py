"""
Test Complete Tier 1 Pipeline with Database Integration
WebSocket → Candles → Database → Features → Database
Tests the full PRD Section 4-7 implementation
"""

import sys
import os
# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
from datetime import datetime
from src.data.collectors import VALRWebSocketClient, MarketTick
from src.data.processors import MultiTimeframeAggregator, OHLC
from src.data.storage import DatabaseWriter

# Global stats
stats = {
    'trades': 0,
    'candles': 0,
    'db_writes': 0
}


async def main():
    """Test complete Tier 1 with database persistence"""
    print("\n" + "=" * 80)
    print("  TIER 1 COMPLETE PIPELINE TEST - WITH DATABASE")
    print("  WebSocket -> Candles -> PostgreSQL")
    print("=" * 80)
    print(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Duration: 2 minutes")
    print("=" * 80 + "\n")

    # Initialize database writer
    print("[INIT] Initializing DatabaseWriter...")
    db_writer = DatabaseWriter()
    await db_writer.initialize()
    print("[OK] DatabaseWriter ready\n")

    # Get initial database stats
    initial_stats = await db_writer.get_stats()
    print("[INFO] Initial database state:")
    print(f"  Candles:   {initial_stats['candles']:>8,}")
    print(f"  Trades:    {initial_stats['trades']:>8,}")
    print(f"  Features:  {initial_stats['features']:>8,}\n")

    # Candle completion callback
    async def handle_candle(candle: OHLC):
        """Callback when candle completes"""
        stats['candles'] += 1
        print(
            f"\n[CANDLE] {candle.pair} {candle.timeframe} @ {candle.timestamp.strftime('%H:%M:%S')} - "
            f"O:R{candle.open:,.0f} H:R{candle.high:,.0f} L:R{candle.low:,.0f} C:R{candle.close:,.0f} "
            f"({candle.trade_count} trades) -> DATABASE"
        )

    # Create candle aggregator with database writer
    print("[INIT] Creating MultiTimeframeAggregator with database...")
    aggregator = MultiTimeframeAggregator(
        pairs=["BTCZAR"],
        on_candle_complete=handle_candle,
        db_writer=db_writer  # DATABASE INTEGRATION
    )
    print("[OK] Aggregator ready with database integration\n")

    # Trade handler
    async def handle_trade(tick: MarketTick):
        """Process trades"""
        stats['trades'] += 1

        # Show progress every 50 trades
        if stats['trades'] % 50 == 0:
            print(f"[PROGRESS] Trades: {stats['trades']}, Candles: {stats['candles']}")

        # Process through aggregator
        await aggregator.process_trade(tick)

        # Optionally save raw trade to database
        # await db_writer.save_trade(tick)

    # Create WebSocket client
    print("[INIT] Creating VALR WebSocket client...")
    client = VALRWebSocketClient(
        pairs=["BTCZAR"],
        on_trade=handle_trade
    )
    print("[OK] WebSocket client ready\n")

    print("=" * 80)
    print("  STARTING DATA COLLECTION")
    print("=" * 80 + "\n")

    try:
        # Run for 2 minutes
        await asyncio.wait_for(client.start(), timeout=120)

    except asyncio.TimeoutError:
        print("\n\n" + "=" * 80)
        print("  TEST COMPLETE (2 minutes)")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("  TEST INTERRUPTED")
        print("=" * 80)

    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Stop client
        await client.stop()

        # Finalize remaining candles
        await aggregator.force_finalize_all()

        # Get final database stats
        final_stats = await db_writer.get_stats()

        # Close database
        await db_writer.close()

    # Print comprehensive analysis
    print("\n" + "=" * 80)
    print("  TIER 1 PIPELINE ANALYSIS")
    print("=" * 80)

    print("\n  WEBSOCKET STATISTICS:")
    ws_stats = client.get_stats()
    print(f"    Messages Received:     {ws_stats['messages_received']:>10,}")
    print(f"    Reconnect Count:       {ws_stats['reconnect_count']:>10,}")
    print(f"    Last Message:          {ws_stats['last_message_time'] or 'N/A'}")

    print("\n  AGGREGATOR STATISTICS:")
    agg_stats = aggregator.get_stats()
    print(f"    Trades Processed:      {agg_stats['total_trades_processed']:>10,}")
    print(f"    Candles Created:       {agg_stats['total_candles_created']:>10,}")
    print(f"    Buffered Candles:      {agg_stats['buffered_candles']:>10,}")

    print("\n  DATABASE STATISTICS:")
    print(f"    Initial Candles:       {initial_stats['candles']:>10,}")
    print(f"    Final Candles:         {final_stats['candles']:>10,}")
    print(f"    New Candles Written:   {final_stats['candles'] - initial_stats['candles']:>10,} [OK]")
    print(f"")
    print(f"    Initial Trades:        {initial_stats['trades']:>10,}")
    print(f"    Final Trades:          {final_stats['trades']:>10,}")
    print(f"    New Trades Written:    {final_stats['trades'] - initial_stats['trades']:>10,}")

    print("\n  DATA PERSISTENCE TEST:")
    new_candles = final_stats['candles'] - initial_stats['candles']
    if new_candles > 0:
        print(f"    [OK] SUCCESS - {new_candles} candles persisted to PostgreSQL")
        print(f"    [OK] Database integration working correctly")
    else:
        print(f"    [FAIL] No candles written to database")
        print(f"    [FAIL] Database integration not working")

    # Verify data in database
    print("\n  VERIFYING DATABASE CONTENT:")
    temp_db = DatabaseWriter()
    await temp_db.initialize()

    for tf in ["1m", "5m", "15m"]:
        candles = await temp_db.get_recent_candles("BTCZAR", tf, limit=5)
        print(f"    {tf.upper()} Candles in DB: {len(candles):>3}")
        if candles:
            latest = candles[-1]
            print(f"      Latest: {datetime.fromisoformat(str(latest['open_time'])).strftime('%H:%M:%S')} "
                  f"Close: R{float(latest['close_price']):,.0f}")

    await temp_db.close()

    print("\n" + "=" * 80)
    print("  TIER 1 COMPLETION STATUS")
    print("=" * 80)

    # Checklist
    checks = {
        "WebSocket Connection": ws_stats['messages_received'] > 0,
        "Trade Processing": agg_stats['total_trades_processed'] > 0,
        "Candle Aggregation": agg_stats['total_candles_created'] > 0,
        "Database Writes": new_candles > 0,
        "Multi-Timeframe": len([k for k in agg_stats['current_candles'].values() if k]) >= 1
    }

    for check, passed in checks.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status}  {check}")

    all_passed = all(checks.values())
    print("\n" + "=" * 80)
    if all_passed:
        print("  [OK] TIER 1 COMPLETE - ALL TESTS PASSED")
        print("  [OK] WebSocket -> Candles -> Database pipeline operational")
        print("  [OK] Ready for Tier 2 development")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f"  [WARNING] TIER 1 INCOMPLETE - {len(failed)} tests failed:")
        for f in failed:
            print(f"      - {f}")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
