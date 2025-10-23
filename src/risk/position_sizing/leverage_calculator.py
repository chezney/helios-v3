"""
Dynamic Leverage Calculator

Calculates leverage based on:
- ML prediction confidence
- Volatility regime
- Current drawdown

Leverage Formula:
Base (1.0x) + Confidence Bonus + Volatility Penalty + Drawdown Penalty
Clamped to [1.0x, 3.0x]
"""

from typing import Dict

from config.risk_config import LEVERAGE_CONFIG, REGIME_PENALTIES
from src.utils.logger import get_logger

logger = get_logger(__name__, component="leverage_calculator")


class DynamicLeverageCalculator:
    """
    Calculate dynamic leverage based on market conditions and confidence.

    Leverage increases with higher confidence and decreases with:
    - Higher volatility
    - Larger drawdowns
    """

    def __init__(self):
        self.base_leverage = LEVERAGE_CONFIG['base_leverage']
        self.max_leverage = LEVERAGE_CONFIG['max_leverage']
        self.confidence_threshold = LEVERAGE_CONFIG['confidence_threshold']
        self.confidence_multiplier = LEVERAGE_CONFIG['confidence_multiplier']
        self.drawdown_threshold = LEVERAGE_CONFIG['drawdown_threshold']
        self.drawdown_penalty = LEVERAGE_CONFIG['drawdown_penalty']

    def calculate_leverage(
        self,
        confidence: float,
        volatility_regime: str,
        current_drawdown_pct: float
    ) -> float:
        """
        Calculate dynamic leverage.

        Args:
            confidence: ML prediction confidence (0.0 to 1.0)
            volatility_regime: Volatility regime (LOW/MEDIUM/HIGH/EXTREME)
            current_drawdown_pct: Current drawdown percentage

        Returns:
            Leverage multiplier (1.0x to 3.0x)
        """
        # Start with base leverage (no leverage)
        leverage = self.base_leverage

        # Add confidence bonus (only for high confidence)
        confidence_bonus = self._calculate_confidence_bonus(confidence)
        leverage += confidence_bonus

        # Subtract volatility penalty
        volatility_penalty = self._calculate_volatility_penalty(volatility_regime)
        leverage += volatility_penalty  # Note: penalty is negative

        # Subtract drawdown penalty
        drawdown_penalty_value = self._calculate_drawdown_penalty(current_drawdown_pct)
        leverage += drawdown_penalty_value  # Note: penalty is negative

        # Clamp to [1.0, 3.0]
        final_leverage = max(self.base_leverage, min(self.max_leverage, leverage))

        logger.debug(
            f"Leverage calculation: Base={self.base_leverage}, "
            f"Confidence bonus={confidence_bonus:+.2f}, "
            f"Volatility penalty={volatility_penalty:+.2f}, "
            f"Drawdown penalty={drawdown_penalty_value:+.2f}, "
            f"Final={final_leverage:.2f}x"
        )

        return final_leverage

    def _calculate_confidence_bonus(self, confidence: float) -> float:
        """
        Calculate confidence bonus for leverage.

        Only add leverage if confidence > 0.70
        Max bonus: +0.60 for 100% confidence
        """
        if confidence <= self.confidence_threshold:
            return 0.0

        # Linear scaling from threshold to 1.0
        # confidence 0.70 → 0.0 bonus
        # confidence 1.00 → 0.60 bonus (0.30 * 2.0 multiplier)
        confidence_above_threshold = confidence - self.confidence_threshold
        max_confidence_range = 1.0 - self.confidence_threshold  # 0.30

        bonus = (confidence_above_threshold / max_confidence_range) * \
                (max_confidence_range * self.confidence_multiplier)

        return bonus

    def _calculate_volatility_penalty(self, volatility_regime: str) -> float:
        """
        Calculate volatility penalty for leverage.

        Higher volatility = larger penalty (negative adjustment)
        """
        penalty = REGIME_PENALTIES.get(volatility_regime, -0.3)
        return penalty

    def _calculate_drawdown_penalty(self, current_drawdown_pct: float) -> float:
        """
        Calculate drawdown penalty for leverage.

        Reduce leverage during drawdowns to protect capital.
        """
        if current_drawdown_pct <= self.drawdown_threshold * 100:
            # No penalty if drawdown <= 10%
            return 0.0

        # Apply penalty if in drawdown
        return self.drawdown_penalty
