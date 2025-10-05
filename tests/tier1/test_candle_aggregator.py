"""
Test Multi-Timeframe Candle Aggregator with Live VALR WebSocket Data
Runs for 2 minutes to capture at least two 1-minute candles
"""

import sys
import os
# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
from datetime import datetime
from src.data.collectors import VALRWebSocketClient, MarketTick
from src.data.processors import MultiTimeframeAggregator, OHLC


async def handle_candle(candle: OHLC):
    """Callback when a candle is completed"""
    print(
        f"\n[CANDLE COMPLETED] {candle.pair} {candle.timeframe} @ {candle.timestamp.strftime('%H:%M:%S')}\n"
        f"  Open:   R{candle.open:>12,.2f}\n"
        f"  High:   R{candle.high:>12,.2f}\n"
        f"  Low:    R{candle.low:>12,.2f}\n"
        f"  Close:  R{candle.close:>12,.2f}\n"
        f"  Volume: {candle.volume:>12,.4f}\n"
        f"  Trades: {candle.trade_count:>12,}\n"
    )


async def main():
    """Test candle aggregator with live WebSocket data"""
    print("\n" + "=" * 80)
    print("  VALR Multi-Timeframe Candle Aggregator Test")
    print("=" * 80)
    print(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Timeframes: 1min, 5min, 15min")
    print(f"  Duration: 2 minutes (to capture at least 2 complete 1min candles)")
    print("=" * 80 + "\n")

    # Create aggregator
    aggregator = MultiTimeframeAggregator(
        pairs=["BTCZAR"],
        on_candle_complete=handle_candle
    )

    # Track trade count for progress
    trade_count = 0

    # Create WebSocket client with aggregator callback
    async def handle_trade(tick: MarketTick):
        """Process trades through aggregator"""
        nonlocal trade_count
        trade_count += 1

        # Show periodic progress
        if trade_count % 10 == 0:
            print(f"[PROGRESS] Processed {trade_count} trades - Last: {tick.pair} @ R{tick.price:,.2f}")

        await aggregator.process_trade(tick)

    client = VALRWebSocketClient(
        pairs=["BTCZAR"],
        on_trade=handle_trade
    )

    try:
        # Start WebSocket client
        print("Connecting to VALR WebSocket...\n")

        # Run for 2 minutes to see at least 2 complete 1min candles
        await asyncio.wait_for(client.start(), timeout=120)

    except asyncio.TimeoutError:
        print("\n\n" + "=" * 80)
        print("  Test Duration Complete (2 minutes)")
        print("=" * 80)
        await client.stop()
        await aggregator.force_finalize_all()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("  Test Interrupted by User")
        print("=" * 80)
        await client.stop()
        await aggregator.force_finalize_all()
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        await client.stop()
        await aggregator.force_finalize_all()

    # Print final statistics
    stats = aggregator.get_stats()
    ws_stats = client.get_stats()

    print("\n" + "=" * 80)
    print("  FINAL STATISTICS")
    print("=" * 80)
    print(f"  WebSocket Messages Received: {ws_stats['messages_received']}")
    print(f"  Trades Processed:            {stats['total_trades_processed']}")
    print(f"  Candles Created:             {stats['total_candles_created']}")
    print(f"  Buffered Candles:            {stats['buffered_candles']}")
    print(f"  Reconnect Count:             {ws_stats['reconnect_count']}")
    print("=" * 80)

    # Show recent candles for each timeframe
    for tf in ["1m", "5m", "15m"]:
        candles = aggregator.get_recent_candles("BTCZAR", tf, limit=10)
        print(f"\n  {tf.upper()} Candles ({len(candles)} completed):")

        if candles:
            print("  " + "-" * 76)
            print(f"  {'Time':<10} {'Open':>12} {'High':>12} {'Low':>12} {'Close':>12} {'Volume':>10}")
            print("  " + "-" * 76)

            for c in candles[-5:]:  # Show last 5
                print(
                    f"  {c.timestamp.strftime('%H:%M:%S'):<10} "
                    f"R{c.open:>11,.2f} R{c.high:>11,.2f} R{c.low:>11,.2f} "
                    f"R{c.close:>11,.2f} {c.volume:>10,.2f}"
                )
        else:
            print("  (No completed candles yet)")

    print("\n" + "=" * 80)
    print("  Test Complete")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
