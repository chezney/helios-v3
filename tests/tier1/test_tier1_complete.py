"""
Test Complete Tier 1 Data Pipeline
WebSocket → Candle Aggregation → Feature Engineering
Tests the full data ingestion and feature generation system
"""

import sys
import os
# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
import numpy as np
from datetime import datetime
from src.data.collectors import VALRWebSocketClient, MarketTick
from src.data.processors import MultiTimeframeAggregator, OHLC, FeatureEngineer, FeatureVector


# Global statistics
stats = {
    'trades_processed': 0,
    'candles_created': 0,
    'features_calculated': 0,
    'candles_1m': [],
    'candles_5m': [],
    'candles_15m': []
}


async def handle_candle(candle: OHLC):
    """Callback when a candle is completed"""
    stats['candles_created'] += 1

    # Store candles for feature engineering
    if candle.timeframe == "1m":
        stats['candles_1m'].append(candle)
    elif candle.timeframe == "5m":
        stats['candles_5m'].append(candle)
    elif candle.timeframe == "15m":
        stats['candles_15m'].append(candle)

    print(
        f"\n[CANDLE] {candle.pair} {candle.timeframe} @ {candle.timestamp.strftime('%H:%M:%S')} - "
        f"O:R{candle.open:,.0f} H:R{candle.high:,.0f} L:R{candle.low:,.0f} C:R{candle.close:,.0f} "
        f"({candle.trade_count} trades)"
    )


async def calculate_features_periodically(
    aggregator: MultiTimeframeAggregator,
    engineer: FeatureEngineer,
    pair: str
):
    """Calculate features every 30 seconds if we have enough data"""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds

        # Get recent candles
        candles_1m = stats['candles_1m']
        candles_5m = stats['candles_5m']
        candles_15m = stats['candles_15m']

        # Check if we have enough data (need 50 candles per timeframe)
        if len(candles_1m) >= 50 and len(candles_5m) >= 50 and len(candles_15m) >= 50:
            # Calculate features
            feature_vector = engineer.calculate_features(
                candles_1m=candles_1m[-50:],  # Last 50 candles
                candles_5m=candles_5m[-50:],
                candles_15m=candles_15m[-50:],
                pair=pair
            )

            if feature_vector:
                stats['features_calculated'] += 1

                print("\n" + "=" * 80)
                print(f"  FEATURE VECTOR CALCULATED #{stats['features_calculated']}")
                print("=" * 80)
                print(f"  Timestamp: {feature_vector.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Total Features: {len(feature_vector.features)}")
                print(f"  Feature Shape: {feature_vector.features.shape}")
                print(f"  Feature Stats:")
                print(f"    Mean:   {np.mean(feature_vector.features):>10.6f}")
                print(f"    Std:    {np.std(feature_vector.features):>10.6f}")
                print(f"    Min:    {np.min(feature_vector.features):>10.6f}")
                print(f"    Max:    {np.max(feature_vector.features):>10.6f}")

                # Show sample features (first 10 from each timeframe)
                print(f"\n  Sample Features (1min timeframe):")
                for i in range(min(10, len(feature_vector.features))):
                    feature_name = feature_vector.feature_names[i]
                    feature_value = feature_vector.features[i]
                    print(f"    {feature_name:<30} = {feature_value:>10.6f}")

                print("=" * 80 + "\n")
        else:
            print(
                f"\n[WAITING FOR DATA] "
                f"1m:{len(candles_1m)}/50, 5m:{len(candles_5m)}/50, 15m:{len(candles_15m)}/50"
            )


async def main():
    """Test complete Tier 1 pipeline"""
    print("\n" + "=" * 80)
    print("  TIER 1 COMPLETE PIPELINE TEST")
    print("  WebSocket -> Candle Aggregation -> Feature Engineering")
    print("=" * 80)
    print(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Duration: 2 minutes")
    print(f"  Pair: BTCZAR")
    print("=" * 80 + "\n")

    # Create feature engineer
    engineer = FeatureEngineer()
    print(f"[INIT] Feature Engineer initialized with {len(engineer.all_feature_names)} features\n")

    # Create candle aggregator
    aggregator = MultiTimeframeAggregator(
        pairs=["BTCZAR"],
        on_candle_complete=handle_candle
    )
    print(f"[INIT] Candle Aggregator initialized for 3 timeframes (1m, 5m, 15m)\n")

    # Create WebSocket client with aggregator callback
    async def handle_trade(tick: MarketTick):
        """Process trades through aggregator"""
        stats['trades_processed'] += 1

        # Show periodic progress (every 50 trades)
        if stats['trades_processed'] % 50 == 0:
            print(
                f"[PROGRESS] Trades: {stats['trades_processed']}, "
                f"Candles: {stats['candles_created']}, "
                f"Features: {stats['features_calculated']}"
            )

        await aggregator.process_trade(tick)

    client = VALRWebSocketClient(
        pairs=["BTCZAR"],
        on_trade=handle_trade
    )

    print("[INIT] WebSocket Client initialized\n")
    print("Connecting to VALR WebSocket...\n")

    # Start feature calculation task
    feature_task = asyncio.create_task(
        calculate_features_periodically(aggregator, engineer, "BTCZAR")
    )

    try:
        # Run for 2 minutes to test the pipeline
        await asyncio.wait_for(client.start(), timeout=120)

    except asyncio.TimeoutError:
        print("\n\n" + "=" * 80)
        print("  Test Complete (2 minutes)")
        print("=" * 80)
        feature_task.cancel()
        await client.stop()
        await aggregator.force_finalize_all()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("  Test Interrupted by User")
        print("=" * 80)
        feature_task.cancel()
        await client.stop()
        await aggregator.force_finalize_all()
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        feature_task.cancel()
        await client.stop()
        await aggregator.force_finalize_all()

    # Final statistics
    ws_stats = client.get_stats()
    agg_stats = aggregator.get_stats()

    print("\n" + "=" * 80)
    print("  FINAL STATISTICS")
    print("=" * 80)
    print(f"  WebSocket Messages:  {ws_stats['messages_received']:>10,}")
    print(f"  Trades Processed:    {stats['trades_processed']:>10,}")
    print(f"  Candles Created:     {stats['candles_created']:>10,}")
    print(f"    - 1min candles:    {len(stats['candles_1m']):>10,}")
    print(f"    - 5min candles:    {len(stats['candles_5m']):>10,}")
    print(f"    - 15min candles:   {len(stats['candles_15m']):>10,}")
    print(f"  Features Calculated: {stats['features_calculated']:>10,}")
    print(f"  Reconnects:          {ws_stats['reconnect_count']:>10,}")
    print("=" * 80)

    # Show final candle data summary
    print("\n  CANDLE DATA SUMMARY:")
    print("  " + "-" * 76)

    for tf in ["1m", "5m", "15m"]:
        candles = aggregator.get_recent_candles("BTCZAR", tf, limit=5)
        if candles:
            latest = candles[-1]
            print(
                f"  {tf.upper()}: {len(candles)} total, "
                f"Latest @ {latest.timestamp.strftime('%H:%M:%S')} - "
                f"Close: R{latest.close:,.0f}, Vol: {latest.volume:,.2f}"
            )

    # Final feature calculation with all available data
    print("\n  FINAL FEATURE CALCULATION:")
    print("  " + "-" * 76)

    if len(stats['candles_1m']) >= 50 and len(stats['candles_5m']) >= 50 and len(stats['candles_15m']) >= 50:
        final_features = engineer.calculate_features(
            candles_1m=stats['candles_1m'][-50:],
            candles_5m=stats['candles_5m'][-50:],
            candles_15m=stats['candles_15m'][-50:],
            pair="BTCZAR"
        )

        if final_features:
            print(f"  Total Features:      {len(final_features.features)}")
            print(f"  Feature Mean:        {np.mean(final_features.features):>10.6f}")
            print(f"  Feature Std:         {np.std(final_features.features):>10.6f}")
            print(f"  Non-zero Features:   {np.count_nonzero(final_features.features)}")
            print(f"  Zero Features:       {np.sum(final_features.features == 0)}")

            # Check for NaN or Inf
            nan_count = np.isnan(final_features.features).sum()
            inf_count = np.isinf(final_features.features).sum()
            print(f"  NaN Features:        {nan_count}")
            print(f"  Inf Features:        {inf_count}")

            if nan_count == 0 and inf_count == 0:
                print("\n  [OK] Feature vector is clean (no NaN or Inf values)")
                print("  [OK] Tier 1 pipeline fully operational!")
            else:
                print("\n  [WARNING] Feature vector contains NaN or Inf values")
    else:
        print(f"  [INFO] Insufficient data for final feature calculation")
        print(f"         1m:{len(stats['candles_1m'])}/50, 5m:{len(stats['candles_5m'])}/50, 15m:{len(stats['candles_15m'])}/50")

    print("\n" + "=" * 80)
    print("  TIER 1 TEST COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
