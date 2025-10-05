"""
Helios Trading System V3.0 - Tier 1: Feature Engineering
Calculates 90 technical indicators across 3 timeframes (30 per timeframe)
Following PRD Section 8: Feature Engineering
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from src.utils.logger import get_logger
from src.data.processors import OHLC

logger = get_logger(__name__, component="tier1_features")


@dataclass
class FeatureVector:
    """Complete feature vector for ML model input"""
    pair: str
    timestamp: datetime
    features: np.ndarray  # 90 features (30 per timeframe)
    feature_names: List[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "pair": self.pair,
            "timestamp": self.timestamp.isoformat(),
            "features": self.features.tolist(),
            "feature_names": self.feature_names
        }


class FeatureEngineer:
    """
    Calculates 90 technical indicators across 3 timeframes.

    Features per timeframe (30 total):
    - Price-based: Returns, log returns, normalized price (3)
    - Moving averages: SMA/EMA 5, 10, 20, 50 (8)
    - Momentum: RSI, MACD, Stochastic, ROC (7)
    - Volatility: ATR, Bollinger Bands, historical volatility (4)
    - Volume: Volume SMA, volume ratio, VWAP (3)
    - Microstructure: Spread, depth imbalance, tick direction (3)
    - Statistical: Skew, kurtosis (2)

    Total: 30 features × 3 timeframes = 90 features
    """

    def __init__(self):
        """Initialize feature engineer"""
        self.feature_names_1m = self._generate_feature_names("1m")
        self.feature_names_5m = self._generate_feature_names("5m")
        self.feature_names_15m = self._generate_feature_names("15m")

        self.all_feature_names = (
            self.feature_names_1m +
            self.feature_names_5m +
            self.feature_names_15m
        )

        logger.info(f"FeatureEngineer initialized with {len(self.all_feature_names)} features")

    def _generate_feature_names(self, timeframe: str) -> List[str]:
        """Generate feature names for a timeframe"""
        features = []

        # Price-based (3)
        features.extend([
            f"{timeframe}_return",
            f"{timeframe}_log_return",
            f"{timeframe}_norm_price"
        ])

        # Moving averages (8)
        for period in [5, 10, 20, 50]:
            features.append(f"{timeframe}_sma_{period}")
            features.append(f"{timeframe}_ema_{period}")

        # Momentum (7)
        features.extend([
            f"{timeframe}_rsi_14",
            f"{timeframe}_macd",
            f"{timeframe}_macd_signal",
            f"{timeframe}_macd_hist",
            f"{timeframe}_stoch_k",
            f"{timeframe}_stoch_d",
            f"{timeframe}_roc_10"
        ])

        # Volatility (4)
        features.extend([
            f"{timeframe}_atr_14",
            f"{timeframe}_bb_upper",
            f"{timeframe}_bb_lower",
            f"{timeframe}_hist_vol_20"
        ])

        # Volume (3)
        features.extend([
            f"{timeframe}_volume_sma_20",
            f"{timeframe}_volume_ratio",
            f"{timeframe}_vwap"
        ])

        # Microstructure (3)
        features.extend([
            f"{timeframe}_spread",
            f"{timeframe}_depth_imbalance",
            f"{timeframe}_tick_direction"
        ])

        # Statistical (2)
        features.extend([
            f"{timeframe}_skew_20",
            f"{timeframe}_kurtosis_20"
        ])

        return features

    def calculate_features(
        self,
        candles_1m: List[OHLC],
        candles_5m: List[OHLC],
        candles_15m: List[OHLC],
        pair: str
    ) -> Optional[FeatureVector]:
        """
        Calculate complete 90-feature vector.

        Args:
            candles_1m: List of 1-minute OHLC candles (need at least 50)
            candles_5m: List of 5-minute OHLC candles (need at least 50)
            candles_15m: List of 15-minute OHLC candles (need at least 50)
            pair: Trading pair

        Returns:
            FeatureVector with 90 features or None if insufficient data
        """
        # Check minimum data requirements
        if len(candles_1m) < 50 or len(candles_5m) < 50 or len(candles_15m) < 50:
            logger.warning(
                f"Insufficient candles for feature calculation: "
                f"1m={len(candles_1m)}, 5m={len(candles_5m)}, 15m={len(candles_15m)}"
            )
            return None

        try:
            # Calculate features for each timeframe
            features_1m = self._calculate_timeframe_features(candles_1m, "1m")
            features_5m = self._calculate_timeframe_features(candles_5m, "5m")
            features_15m = self._calculate_timeframe_features(candles_15m, "15m")

            # Combine all features
            all_features = np.concatenate([features_1m, features_5m, features_15m])

            # Get latest timestamp
            timestamp = candles_1m[-1].timestamp

            return FeatureVector(
                pair=pair,
                timestamp=timestamp,
                features=all_features,
                feature_names=self.all_feature_names
            )

        except Exception as e:
            logger.error(f"Error calculating features: {e}", exc_info=True)
            return None

    def _calculate_timeframe_features(self, candles: List[OHLC], timeframe: str) -> np.ndarray:
        """Calculate 30 features for a single timeframe"""
        # Convert candles to DataFrame
        df = self._candles_to_dataframe(candles)

        features = []

        # 1. Price-based features (3)
        features.extend(self._price_features(df))

        # 2. Moving averages (8)
        features.extend(self._moving_average_features(df))

        # 3. Momentum indicators (7)
        features.extend(self._momentum_features(df))

        # 4. Volatility indicators (4)
        features.extend(self._volatility_features(df))

        # 5. Volume features (3)
        features.extend(self._volume_features(df))

        # 6. Microstructure features (3)
        features.extend(self._microstructure_features(df))

        # 7. Statistical features (2)
        features.extend(self._statistical_features(df))

        return np.array(features, dtype=np.float32)

    def _candles_to_dataframe(self, candles: List[OHLC]) -> pd.DataFrame:
        """Convert OHLC candles to pandas DataFrame"""
        data = {
            'open': [c.open for c in candles],
            'high': [c.high for c in candles],
            'low': [c.low for c in candles],
            'close': [c.close for c in candles],
            'volume': [c.volume for c in candles],
            'timestamp': [c.timestamp for c in candles]
        }
        return pd.DataFrame(data)

    def _price_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate price-based features (3)"""
        close = df['close'].values

        # Simple return
        ret = (close[-1] - close[-2]) / close[-2] if len(close) > 1 else 0.0

        # Log return
        log_ret = np.log(close[-1] / close[-2]) if len(close) > 1 and close[-2] > 0 else 0.0

        # Normalized price (z-score over last 20 periods)
        if len(close) >= 20:
            mean = np.mean(close[-20:])
            std = np.std(close[-20:])
            norm_price = (close[-1] - mean) / std if std > 0 else 0.0
        else:
            norm_price = 0.0

        return [ret, log_ret, norm_price]

    def _moving_average_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate moving average features (8)"""
        close = df['close'].values
        features = []

        for period in [5, 10, 20, 50]:
            # SMA
            if len(close) >= period:
                sma = np.mean(close[-period:])
                features.append((close[-1] - sma) / sma if sma > 0 else 0.0)
            else:
                features.append(0.0)

            # EMA
            if len(close) >= period:
                ema = self._calculate_ema(close, period)
                features.append((close[-1] - ema) / ema if ema > 0 else 0.0)
            else:
                features.append(0.0)

        return features

    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        alpha = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema

        return ema

    def _momentum_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate momentum indicators (7)"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        features = []

        # RSI (14-period)
        if len(close) >= 15:
            rsi = self._calculate_rsi(close, 14)
            features.append(rsi / 100.0)  # Normalize to 0-1
        else:
            features.append(0.5)

        # MACD (12, 26, 9)
        if len(close) >= 26:
            macd, signal, hist = self._calculate_macd(close)
            features.extend([macd, signal, hist])
        else:
            features.extend([0.0, 0.0, 0.0])

        # Stochastic Oscillator (14, 3)
        if len(high) >= 14:
            stoch_k, stoch_d = self._calculate_stochastic(high, low, close, 14, 3)
            features.extend([stoch_k / 100.0, stoch_d / 100.0])
        else:
            features.extend([0.5, 0.5])

        # Rate of Change (10-period)
        if len(close) >= 11:
            roc = (close[-1] - close[-11]) / close[-11] if close[-11] > 0 else 0.0
            features.append(roc)
        else:
            features.append(0.0)

        return features

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        deltas = np.diff(prices)

        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(self, prices: np.ndarray) -> tuple:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)

        macd = ema_12 - ema_26

        # For signal line, we'd need to calculate EMA of MACD values
        # Simplified: use normalized MACD
        macd_norm = macd / prices[-1] if prices[-1] > 0 else 0.0
        signal = macd_norm * 0.9  # Simplified signal
        hist = macd_norm - signal

        return macd_norm, signal, hist

    def _calculate_stochastic(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        k_period: int = 14,
        d_period: int = 3
    ) -> tuple:
        """Calculate Stochastic Oscillator"""
        highest_high = np.max(high[-k_period:])
        lowest_low = np.min(low[-k_period:])

        if highest_high == lowest_low:
            stoch_k = 50.0
        else:
            stoch_k = ((close[-1] - lowest_low) / (highest_high - lowest_low)) * 100

        # Simplified %D (should be SMA of %K)
        stoch_d = stoch_k * 0.95  # Simplified

        return stoch_k, stoch_d

    def _volatility_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate volatility indicators (4)"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        features = []

        # ATR (Average True Range, 14-period)
        if len(close) >= 15:
            atr = self._calculate_atr(high, low, close, 14)
            features.append(atr / close[-1] if close[-1] > 0 else 0.0)
        else:
            features.append(0.0)

        # Bollinger Bands (20-period, 2 std)
        if len(close) >= 20:
            bb_upper, bb_lower = self._calculate_bollinger_bands(close, 20, 2)
            features.append((bb_upper - close[-1]) / close[-1] if close[-1] > 0 else 0.0)
            features.append((close[-1] - bb_lower) / close[-1] if close[-1] > 0 else 0.0)
        else:
            features.extend([0.0, 0.0])

        # Historical volatility (20-period)
        if len(close) >= 21:
            returns = np.diff(np.log(close[-21:]))
            hist_vol = np.std(returns) * np.sqrt(252)  # Annualized
            features.append(hist_vol)
        else:
            features.append(0.0)

        return features

    def _calculate_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> float:
        """Calculate Average True Range"""
        tr_list = []

        for i in range(1, len(close)):
            h_l = high[i] - low[i]
            h_pc = abs(high[i] - close[i - 1])
            l_pc = abs(low[i] - close[i - 1])

            tr = max(h_l, h_pc, l_pc)
            tr_list.append(tr)

        atr = np.mean(tr_list[-period:]) if len(tr_list) >= period else 0.0
        return atr

    def _calculate_bollinger_bands(self, prices: np.ndarray, period: int, num_std: float) -> tuple:
        """Calculate Bollinger Bands"""
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])

        upper = sma + (num_std * std)
        lower = sma - (num_std * std)

        return upper, lower

    def _volume_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate volume features (3)"""
        volume = df['volume'].values
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        features = []

        # Volume SMA (20-period)
        if len(volume) >= 20:
            volume_sma = np.mean(volume[-20:])
            features.append((volume[-1] - volume_sma) / volume_sma if volume_sma > 0 else 0.0)
        else:
            features.append(0.0)

        # Volume ratio (current vs average)
        if len(volume) >= 10:
            avg_volume = np.mean(volume[-10:])
            volume_ratio = volume[-1] / avg_volume if avg_volume > 0 else 1.0
            features.append(volume_ratio)
        else:
            features.append(1.0)

        # VWAP (Volume Weighted Average Price)
        if len(volume) >= 20 and np.sum(volume[-20:]) > 0:
            typical_prices = (high[-20:] + low[-20:] + close[-20:]) / 3
            vwap = np.sum(typical_prices * volume[-20:]) / np.sum(volume[-20:])
            features.append((close[-1] - vwap) / vwap if vwap > 0 else 0.0)
        else:
            features.append(0.0)

        return features

    def _microstructure_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate microstructure features (3)"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values

        features = []

        # Spread (high-low relative to close)
        spread = (high[-1] - low[-1]) / close[-1] if close[-1] > 0 else 0.0
        features.append(spread)

        # Depth imbalance (simplified: based on close position in range)
        if high[-1] != low[-1]:
            depth_imbalance = (close[-1] - low[-1]) / (high[-1] - low[-1])
        else:
            depth_imbalance = 0.5
        features.append(depth_imbalance)

        # Tick direction (up/down based on last 3 closes)
        if len(close) >= 3:
            if close[-1] > close[-2]:
                tick_dir = 1.0
            elif close[-1] < close[-2]:
                tick_dir = -1.0
            else:
                tick_dir = 0.0
        else:
            tick_dir = 0.0
        features.append(tick_dir)

        return features

    def _statistical_features(self, df: pd.DataFrame) -> List[float]:
        """Calculate statistical features (2)"""
        close = df['close'].values

        features = []

        # Skewness (20-period)
        if len(close) >= 20:
            returns = np.diff(np.log(close[-21:]))
            skew = self._calculate_skewness(returns)
            features.append(skew)
        else:
            features.append(0.0)

        # Kurtosis (20-period)
        if len(close) >= 20:
            returns = np.diff(np.log(close[-21:]))
            kurt = self._calculate_kurtosis(returns)
            features.append(kurt)
        else:
            features.append(0.0)

        return features

    def _calculate_skewness(self, data: np.ndarray) -> float:
        """Calculate skewness"""
        if len(data) == 0:
            return 0.0

        mean = np.mean(data)
        std = np.std(data)

        if std == 0:
            return 0.0

        skew = np.mean(((data - mean) / std) ** 3)
        return skew

    def _calculate_kurtosis(self, data: np.ndarray) -> float:
        """Calculate kurtosis (excess kurtosis)"""
        if len(data) == 0:
            return 0.0

        mean = np.mean(data)
        std = np.std(data)

        if std == 0:
            return 0.0

        kurt = np.mean(((data - mean) / std) ** 4) - 3  # Excess kurtosis
        return kurt
