"""
Trading execution module.

Provides paper and live trading clients for order execution.
"""

from .paper_trading_client import PaperTradingClient

__all__ = ['PaperTradingClient']
