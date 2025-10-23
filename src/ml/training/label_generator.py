"""
Label Generator for Helios Trading System.

Generates BUY/SELL/HOLD labels from historical price data using look-ahead strategy.
PRD Section 11.1: Label Generation Strategy
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class LabelGenerator:
    """
    Generate trading labels from historical price data.

    Strategy: Look ahead N candles, classify based on price movement.

    Example:
        If price rises >2% in next 12 candles: BUY (we should have bought)
        If price falls >2% in next 12 candles: SELL (we should have sold)
        Otherwise: HOLD
    """

    def __init__(
        self,
        look_ahead_candles: int = 12,  # 12 × 5min = 1 hour ahead
        buy_threshold_pct: float = 0.02,  # 2% gain
        sell_threshold_pct: float = 0.02,  # 2% loss
    ):
        self.look_ahead = look_ahead_candles
        self.buy_threshold = buy_threshold_pct
        self.sell_threshold = sell_threshold_pct

        logger.info(
            f"LabelGenerator initialized: look_ahead={look_ahead_candles}, "
            f"buy_threshold={buy_threshold_pct:.2%}, "
            f"sell_threshold={sell_threshold_pct:.2%}"
        )

    def generate_labels(self, df: pd.DataFrame) -> pd.Series:
        """
        Generate BUY/SELL/HOLD labels.

        Logic:
        - Look ahead N candles
        - If price rises >threshold: BUY (0)
        - If price falls >threshold: SELL (1)
        - Otherwise: HOLD (2)

        Args:
            df: DataFrame with 'close_price' column

        Returns:
            Series of labels (0=BUY, 1=SELL, 2=HOLD, None=unlabeled)
        """
        labels = []

        for i in range(len(df)):
            # Can't label last N candles (no future data)
            if i >= len(df) - self.look_ahead:
                labels.append(None)
                continue

            current_price = df["close_price"].iloc[i]
            future_price = df["close_price"].iloc[i + self.look_ahead]

            # Skip invalid prices (zero or None)
            if current_price == 0 or future_price == 0 or pd.isna(current_price) or pd.isna(future_price):
                labels.append(None)
                continue

            # Calculate future return
            future_return = (future_price - current_price) / current_price

            # Classify
            if future_return > self.buy_threshold:
                labels.append(0)  # BUY
            elif future_return < -self.sell_threshold:
                labels.append(1)  # SELL
            else:
                labels.append(2)  # HOLD

        return pd.Series(labels, index=df.index)

    def get_class_distribution(self, labels: pd.Series) -> dict:
        """
        Get class distribution statistics.

        Args:
            labels: Series of labels

        Returns:
            Dictionary with class counts and percentages
        """
        # Remove None values
        valid_labels = labels.dropna()

        total = len(valid_labels)
        if total == 0:
            return {
                "BUY": {"count": 0, "pct": 0.0},
                "SELL": {"count": 0, "pct": 0.0},
                "HOLD": {"count": 0, "pct": 0.0},
                "total": 0
            }

        buy_count = (valid_labels == 0).sum()
        sell_count = (valid_labels == 1).sum()
        hold_count = (valid_labels == 2).sum()

        return {
            "BUY": {"count": int(buy_count), "pct": buy_count / total},
            "SELL": {"count": int(sell_count), "pct": sell_count / total},
            "HOLD": {"count": int(hold_count), "pct": hold_count / total},
            "total": int(total),
        }
