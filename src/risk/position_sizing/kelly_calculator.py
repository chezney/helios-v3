"""
Kelly Criterion Position Sizing Calculator

Implements Kelly Criterion with fractional Kelly, volatility adjustments,
and regime-based position caps.

Classic Kelly Formula:
f* = (p·b - q) / b

Where:
- f*: Optimal fraction of capital to allocate
- p: Probability of winning (ML confidence)
- q: Probability of losing (1 - p)
- b: Reward/risk ratio
"""

import numpy as np
from typing import Optional
from datetime import datetime

from config.risk_config import (
    KELLY_CONFIG,
    REGIME_CAPS,
    RISK_CONTROLS
)
from src.utils.logger import get_logger
from src.risk.position_sizing.models import PositionSizeResult

logger = get_logger(__name__, component="kelly_calculator")


class KellyPositionSizer:
    """
    Kelly Criterion position sizing calculator.

    Calculates optimal position sizes using Kelly formula with:
    - Fractional Kelly (0.25x for safety)
    - Volatility adjustments
    - Drawdown protection
    - Regime-based caps
    """

    def __init__(self):
        self.fractional_kelly = KELLY_CONFIG['fractional_kelly']
        self.reward_risk_ratio = KELLY_CONFIG['reward_risk_ratio']
        self.min_confidence = KELLY_CONFIG['min_confidence']
        self.max_position_pct = KELLY_CONFIG['max_position_pct']
        self.stop_loss_multiplier = RISK_CONTROLS['stop_loss_volatility_multiplier']
        self.reward_risk = RISK_CONTROLS['reward_risk_ratio']
        self.max_hold_time = RISK_CONTROLS['max_hold_time_hours']

    def calculate_position_size(
        self,
        pair: str,
        signal: str,
        confidence: float,
        portfolio_value_zar: float,
        current_volatility: float,
        volatility_regime: str,
        current_drawdown_pct: float,
        max_probability: float = None
    ) -> Optional[PositionSizeResult]:
        """
        Calculate position size using Kelly Criterion.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: Trading signal (BUY or SELL)
            confidence: ML prediction confidence (0.0 to 1.0)
            portfolio_value_zar: Current portfolio value in ZAR
            current_volatility: Daily volatility forecast
            volatility_regime: Volatility regime (LOW/MEDIUM/HIGH/EXTREME)
            current_drawdown_pct: Current drawdown percentage
            max_probability: Maximum probability from ML prediction

        Returns:
            PositionSizeResult if valid trade, None otherwise
        """
        # Validation: Don't trade on HOLD signals
        if signal == 'HOLD':
            logger.debug("Skipping HOLD signal")
            return None

        # Validation: Don't trade if confidence too low
        if confidence < self.min_confidence:
            logger.debug(
                f"Confidence {confidence:.2%} below minimum {self.min_confidence:.2%}"
            )
            return None

        # Step 1: Calculate Kelly fraction
        kelly_fraction = self._calculate_kelly_fraction(confidence)

        # Step 2: Apply fractional Kelly multiplier (0.25x for safety)
        fractional_kelly_value = self._apply_fractional_kelly(kelly_fraction)

        # Step 3: Adjust for volatility
        vol_adjusted_fraction = self._adjust_for_volatility(
            fractional_kelly_value,
            volatility_regime
        )

        # Step 4: Adjust for drawdown
        drawdown_adjusted_fraction = self._adjust_for_drawdown(
            vol_adjusted_fraction,
            current_drawdown_pct
        )

        # Step 5: Apply regime-based cap
        final_fraction = self._apply_regime_cap(
            drawdown_adjusted_fraction,
            volatility_regime
        )

        # Step 6: Convert fraction to ZAR position size
        position_size_zar = portfolio_value_zar * final_fraction

        # Step 7: Calculate stop loss percentage
        stop_loss_pct = self._calculate_stop_loss(current_volatility)

        # Step 8: Calculate take profit percentage (2x stop loss for 2:1 RR)
        take_profit_pct = stop_loss_pct * self.reward_risk

        # Create result
        result = PositionSizeResult(
            pair=pair,
            signal=signal,
            confidence=confidence,
            max_probability=max_probability if max_probability else confidence,
            kelly_fraction=kelly_fraction,
            fractional_kelly=fractional_kelly_value,
            volatility_adjusted_fraction=vol_adjusted_fraction,
            position_size_zar=position_size_zar,
            leverage=1.0,  # Default leverage, will be calculated by leverage calculator
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            max_hold_time_hours=self.max_hold_time,
            daily_volatility=current_volatility,
            volatility_regime=volatility_regime,
            portfolio_value_zar=portfolio_value_zar,
            current_drawdown_pct=current_drawdown_pct,
            timestamp=datetime.utcnow()
        )

        logger.info(
            f"Position calculated for {pair}: "
            f"Size={position_size_zar:,.0f} ZAR ({final_fraction:.2%} of portfolio), "
            f"SL={stop_loss_pct:.2f}%, TP={take_profit_pct:.2f}%"
        )

        return result

    def _calculate_kelly_fraction(self, confidence: float) -> float:
        """
        Calculate Kelly fraction using classic formula.

        f* = (p·b - q) / b

        Where:
        - p = confidence (probability of winning)
        - q = 1 - p (probability of losing)
        - b = reward/risk ratio
        """
        p = confidence  # Probability of winning
        q = 1.0 - p     # Probability of losing
        b = self.reward_risk_ratio

        # Kelly formula
        kelly = (p * b - q) / b

        # Kelly can be negative if edge is insufficient
        # In that case, return 0 (don't trade)
        return max(0.0, kelly)

    def _apply_fractional_kelly(self, kelly_fraction: float) -> float:
        """
        Apply fractional Kelly multiplier for safety.

        Fractional Kelly reduces risk of ruin by taking a fraction
        of the full Kelly bet (typically 0.25x or 0.5x).
        """
        return kelly_fraction * self.fractional_kelly

    def _adjust_for_volatility(
        self,
        fraction: float,
        volatility_regime: str
    ) -> float:
        """
        Adjust position size based on volatility regime.

        Higher volatility = smaller positions to control risk.
        """
        # Volatility adjustment factors
        vol_adjustments = {
            'LOW': 1.0,      # No adjustment in low volatility
            'MEDIUM': 0.85,  # Reduce by 15% in medium volatility
            'HIGH': 0.70,    # Reduce by 30% in high volatility
            'EXTREME': 0.50  # Reduce by 50% in extreme volatility
        }

        adjustment = vol_adjustments.get(volatility_regime, 0.85)
        return fraction * adjustment

    def _adjust_for_drawdown(
        self,
        fraction: float,
        current_drawdown_pct: float
    ) -> float:
        """
        Adjust position size during drawdowns.

        Reduce position sizes to protect capital during losing periods.
        """
        if current_drawdown_pct <= 5.0:
            # No adjustment for small drawdowns (<5%)
            return fraction

        elif current_drawdown_pct <= 10.0:
            # Reduce by 20% for 5-10% drawdown
            return fraction * 0.80

        elif current_drawdown_pct <= 15.0:
            # Reduce by 40% for 10-15% drawdown
            return fraction * 0.60

        else:
            # Reduce by 60% for >15% drawdown
            return fraction * 0.40

    def _apply_regime_cap(
        self,
        fraction: float,
        volatility_regime: str
    ) -> float:
        """
        Apply regime-based maximum position caps.

        Ensures we never risk too much in any single position.
        """
        regime_cap = REGIME_CAPS.get(volatility_regime, 0.15)

        # Cap at regime maximum
        capped_fraction = min(fraction, regime_cap)

        # Also cap at global maximum
        final_fraction = min(capped_fraction, self.max_position_pct)

        return final_fraction

    def _calculate_stop_loss(self, daily_volatility: float) -> float:
        """
        Calculate stop loss percentage based on daily volatility.

        Stop loss = 1.5x daily volatility (gives breathing room for normal fluctuations)
        """
        stop_loss_pct = daily_volatility * 100 * self.stop_loss_multiplier

        # Ensure minimum stop loss of 2% and maximum of 10%
        stop_loss_pct = max(2.0, min(10.0, stop_loss_pct))

        return stop_loss_pct
