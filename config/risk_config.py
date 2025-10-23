"""
Risk Management Configuration

Configuration for GARCH volatility modeling, Kelly position sizing,
and dynamic leverage calculation.
"""

from typing import Dict

# GARCH Volatility Configuration
GARCH_CONFIG = {
    'lookback_days': 90,                  # Days of historical data for GARCH fitting
    'min_observations': 60,               # Minimum observations required
    'update_interval_hours': 4,           # Update volatility every 4 hours
    'extreme_move_threshold': 0.05,       # 5% move triggers force update
}

# Volatility regime benchmarks (daily volatility)
# Thresholds vary by asset due to different volatility characteristics
REGIME_BENCHMARKS: Dict[str, Dict[str, float]] = {
    'BTCZAR': {
        'low': 0.02,      # <2% daily vol = LOW
        'medium': 0.04,   # 2-4% = MEDIUM
        'high': 0.06,     # 4-6% = HIGH
                          # >6% = EXTREME
    },
    'ETHZAR': {
        'low': 0.025,     # Ethereum typically more volatile
        'medium': 0.05,
        'high': 0.075,
    },
    'SOLZAR': {
        'low': 0.03,      # Solana even more volatile
        'medium': 0.06,
        'high': 0.09,
    },
}

# Default regime benchmarks for unknown pairs
DEFAULT_REGIME_BENCHMARKS = {
    'low': 0.025,
    'medium': 0.05,
    'high': 0.075,
}

# Kelly Criterion Configuration
KELLY_CONFIG = {
    'fractional_kelly': 0.25,      # Quarter Kelly for safety
    'reward_risk_ratio': 2.0,      # Target 2:1 reward/risk
    'min_confidence': 0.40,        # Don't trade below 40% confidence
    'max_position_pct': 0.20,      # Max 20% of portfolio per position
}

# Regime-based position caps (as fraction of portfolio)
REGIME_CAPS: Dict[str, float] = {
    'LOW': 0.20,        # Max 20% in low volatility
    'MEDIUM': 0.15,     # Max 15% in medium volatility
    'HIGH': 0.10,       # Max 10% in high volatility
    'EXTREME': 0.05,    # Max 5% in extreme volatility
}

# Dynamic leverage configuration
LEVERAGE_CONFIG = {
    'base_leverage': 1.0,              # Start with no leverage
    'max_leverage': 3.0,               # Maximum allowed leverage
    'confidence_threshold': 0.70,      # Only add leverage above 70% confidence
    'confidence_multiplier': 2.0,      # Max +0.60 for 100% confidence (0.30 * 2.0)
    'drawdown_threshold': 0.10,        # Reduce leverage above 10% drawdown
    'drawdown_penalty': -0.5,          # Reduce leverage by 0.5x during drawdowns
}

# Volatility regime penalties for leverage
REGIME_PENALTIES: Dict[str, float] = {
    'LOW': 0.0,         # No penalty in low volatility
    'MEDIUM': -0.3,     # Small reduction in medium volatility
    'HIGH': -0.5,       # Larger reduction in high volatility
    'EXTREME': -1.0,    # Maximum reduction in extreme volatility
}

# Risk control parameters
RISK_CONTROLS = {
    'stop_loss_volatility_multiplier': 1.5,  # SL = 1.5x daily volatility
    'reward_risk_ratio': 2.0,                # TP = 2x SL (2:1 reward/risk)
    'max_hold_time_hours': 24,               # Exit after 24 hours
}
