"""
config/trading_config.py

Spot trading configuration for VALR integration.

Helios V3.0 - Phase 5: Position Manager
Configurable settings for spot trading execution.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class SpotTradingConfig:
    """
    Configuration for spot trading execution on VALR.

    These settings control how the Position Manager executes trades
    and manages stop-loss/take-profit orders on the exchange.
    """

    # Order execution settings
    entry_order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    """Type of order for entry execution (LIMIT recommended for price protection)"""

    order_timeout_seconds: int = 60
    """Maximum time to wait for order fill before timeout (seconds)"""

    accept_partial_fills: bool = True
    """Accept partial fills after timeout and place SL/TP for filled quantity"""

    # Stop-loss / Take-profit settings
    place_sl_tp_on_exchange: bool = True
    """Place TP as limit order on exchange. SL is ALWAYS software-monitored for spot trading."""

    # IMPORTANT: For spot trading, we use a hybrid approach:
    # - TP: Limit order on exchange (passive profit-taking, locks position)
    # - SL: Software monitoring ONLY (active risk protection via monitor_positions)
    #
    # Why? Both TP and SL cannot be limit orders because they'd lock the same balance.
    # Only one can succeed. We prioritize TP on exchange and rely on software for SL.
    #
    # NOTE: SL/TP percentages are calculated dynamically by Phase 5's Aether Risk Engine:
    # - Stop Loss: 1.5x daily volatility (GARCH forecast), min 2%, max 10%
    # - Take Profit: 2x stop_loss (reward/risk ratio = 2.0)
    # These are passed in via trade_params, not hardcoded here.

    # Order monitoring
    order_check_interval_seconds: int = 3
    """Interval between order status checks while waiting for fill (seconds)"""

    # Execution behavior
    limit_order_price_offset_pct: float = 0.1
    """
    Price offset for limit orders (default 0.1% for fast fills).
    Positive = above market (faster BUY fill, slower SELL fill)
    Negative = below market (slower BUY fill, faster SELL fill)

    Note: Testing showed 0.0% offset may not fill quickly on VALR.
    0.1% ensures fast fills while maintaining price protection.
    """

    # Emergency controls
    max_retries_on_error: int = 2
    """Maximum retries if order placement fails"""

    cancel_on_timeout: bool = True
    """Cancel unfilled orders after timeout"""


# Global configuration instance
SPOT_TRADING_CONFIG = SpotTradingConfig()


def get_spot_trading_config() -> SpotTradingConfig:
    """Get the current spot trading configuration."""
    return SPOT_TRADING_CONFIG


def update_spot_trading_config(**kwargs):
    """
    Update spot trading configuration.

    Example:
        update_spot_trading_config(
            order_timeout_seconds=120,
            accept_partial_fills=False
        )
    """
    global SPOT_TRADING_CONFIG

    for key, value in kwargs.items():
        if hasattr(SPOT_TRADING_CONFIG, key):
            setattr(SPOT_TRADING_CONFIG, key, value)
        else:
            raise ValueError(f"Invalid config parameter: {key}")
