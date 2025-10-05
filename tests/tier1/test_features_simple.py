"""
Simple test of feature engineering system
Creates mock candle data and tests feature calculation
"""

import sys
import os
# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import numpy as np
from datetime import datetime, timedelta
from src.data.processors import OHLC, FeatureEngineer


def create_mock_candles(pair: str, timeframe: str, count: int, base_price: float = 2_000_000) -> list:
    """Create mock OHLC candles for testing"""
    candles = []
    timestamp = datetime.now()

    for i in range(count):
        # Simulate price movement
        price_change = np.random.randn() * 1000  # Random walk
        open_price = base_price + price_change
        high_price = open_price + abs(np.random.randn() * 500)
        low_price = open_price - abs(np.random.randn() * 500)
        close_price = open_price + np.random.randn() * 300
        volume = abs(np.random.randn() * 0.1)

        candle = OHLC(
            pair=pair,
            timeframe=timeframe,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_count=int(abs(np.random.randn() * 50))
        )

        candles.append(candle)
        base_price = close_price

        # Increment timestamp based on timeframe
        if timeframe == "1m":
            timestamp += timedelta(minutes=1)
        elif timeframe == "5m":
            timestamp += timedelta(minutes=5)
        elif timeframe == "15m":
            timestamp += timedelta(minutes=15)

    return candles


def main():
    """Test feature engineering with mock data"""
    print("\n" + "=" * 80)
    print("  FEATURE ENGINEERING TEST (Mock Data)")
    print("=" * 80 + "\n")

    # Create feature engineer
    engineer = FeatureEngineer()
    print(f"[INIT] Feature Engineer initialized")
    print(f"  Total Features: {len(engineer.all_feature_names)}")
    print(f"    - 1min features:  {len(engineer.feature_names_1m)}")
    print(f"    - 5min features:  {len(engineer.feature_names_5m)}")
    print(f"    - 15min features: {len(engineer.feature_names_15m)}\n")

    # Create mock candles (need at least 50 per timeframe)
    print("[DATA] Creating mock candle data...")
    candles_1m = create_mock_candles("BTCZAR", "1m", 60, base_price=2_018_000)
    candles_5m = create_mock_candles("BTCZAR", "5m", 60, base_price=2_018_000)
    candles_15m = create_mock_candles("BTCZAR", "15m", 60, base_price=2_018_000)
    print(f"  Created {len(candles_1m)} x 1min candles")
    print(f"  Created {len(candles_5m)} x 5min candles")
    print(f"  Created {len(candles_15m)} x 15min candles\n")

    # Calculate features
    print("[COMPUTE] Calculating features...")
    feature_vector = engineer.calculate_features(
        candles_1m=candles_1m[-50:],
        candles_5m=candles_5m[-50:],
        candles_15m=candles_15m[-50:],
        pair="BTCZAR"
    )

    if not feature_vector:
        print("[ERROR] Feature calculation failed!\n")
        return

    print("[OK] Features calculated successfully!\n")

    # Display results
    print("=" * 80)
    print("  FEATURE VECTOR ANALYSIS")
    print("=" * 80)
    print(f"  Pair:           {feature_vector.pair}")
    print(f"  Timestamp:      {feature_vector.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total Features: {len(feature_vector.features)}")
    print(f"  Feature Shape:  {feature_vector.features.shape}")
    print(f"\n  Statistics:")
    print(f"    Mean:         {np.mean(feature_vector.features):>12.6f}")
    print(f"    Std:          {np.std(feature_vector.features):>12.6f}")
    print(f"    Min:          {np.min(feature_vector.features):>12.6f}")
    print(f"    Max:          {np.max(feature_vector.features):>12.6f}")
    print(f"    Median:       {np.median(feature_vector.features):>12.6f}")
    print(f"\n  Data Quality:")
    print(f"    Non-zero:     {np.count_nonzero(feature_vector.features):>12,}")
    print(f"    Zero:         {np.sum(feature_vector.features == 0):>12,}")
    print(f"    NaN:          {np.isnan(feature_vector.features).sum():>12,}")
    print(f"    Inf:          {np.isinf(feature_vector.features).sum():>12,}")

    # Check data quality
    nan_count = np.isnan(feature_vector.features).sum()
    inf_count = np.isinf(feature_vector.features).sum()

    print("\n" + "=" * 80)
    if nan_count == 0 and inf_count == 0:
        print("  [OK] Feature vector is CLEAN (no NaN or Inf values)")
    else:
        print(f"  [WARNING] Feature vector has {nan_count} NaN and {inf_count} Inf values")

    # Show sample features from each timeframe
    print("\n  SAMPLE FEATURES (First 10 per timeframe):")
    print("  " + "-" * 76)

    # 1min features (0-29)
    print("\n  1-Minute Timeframe Features:")
    for i in range(min(10, 30)):
        name = feature_vector.feature_names[i]
        value = feature_vector.features[i]
        print(f"    {name:<35} = {value:>12.6f}")

    # 5min features (30-59)
    print("\n  5-Minute Timeframe Features:")
    for i in range(30, min(40, 60)):
        name = feature_vector.feature_names[i]
        value = feature_vector.features[i]
        print(f"    {name:<35} = {value:>12.6f}")

    # 15min features (60-89)
    print("\n  15-Minute Timeframe Features:")
    for i in range(60, min(70, 90)):
        name = feature_vector.feature_names[i]
        value = feature_vector.features[i]
        print(f"    {name:<35} = {value:>12.6f}")

    print("\n" + "=" * 80)
    print("  TEST COMPLETE - Feature Engineering System Operational")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
