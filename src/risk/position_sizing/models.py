"""
Position Sizing Data Models

Dataclasses for position sizing results and volatility forecasts.
"""

from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


@dataclass
class PositionSizeResult:
    """
    Complete trade parameters from Aether Risk Engine.

    Contains all information needed to execute a trade:
    - Position size in ZAR
    - Leverage multiplier
    - Stop loss and take profit percentages
    - Risk metrics (Kelly fraction, volatility, etc.)
    """

    # Identification
    pair: str
    signal: str  # BUY or SELL

    # ML prediction inputs
    confidence: float
    max_probability: float

    # Kelly calculation results
    kelly_fraction: float
    fractional_kelly: float
    volatility_adjusted_fraction: float

    # Position parameters
    position_size_zar: float
    leverage: float

    # Risk controls
    stop_loss_pct: float
    take_profit_pct: float
    max_hold_time_hours: int

    # Market conditions
    daily_volatility: float
    volatility_regime: str
    portfolio_value_zar: float
    current_drawdown_pct: float

    # Metadata
    timestamp: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

    @property
    def position_size_crypto(self) -> float:
        """Calculate position size in crypto units (not ZAR)."""
        # This will be calculated when we know the current price
        # For now, return 0.0 as placeholder
        return 0.0

    @property
    def risk_amount_zar(self) -> float:
        """Calculate the ZAR amount at risk (position size * stop loss %)."""
        return self.position_size_zar * (self.stop_loss_pct / 100.0)

    @property
    def potential_profit_zar(self) -> float:
        """Calculate the potential profit in ZAR (position size * take profit %)."""
        return self.position_size_zar * (self.take_profit_pct / 100.0)


@dataclass
class VolatilityForecast:
    """
    GARCH volatility forecast result.

    Contains volatility metrics and regime classification.
    """

    pair: str
    daily_volatility: float
    annualized_volatility: float
    volatility_regime: str  # LOW, MEDIUM, HIGH, EXTREME

    # GARCH model parameters
    garch_omega: float
    garch_alpha: float
    garch_beta: float

    # Metadata
    forecast_timestamp: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['forecast_timestamp'] = self.forecast_timestamp.isoformat()
        return data

    @property
    def is_stationary(self) -> bool:
        """Check if GARCH model is stationary (alpha + beta < 1)."""
        return (self.garch_alpha + self.garch_beta) < 1.0
