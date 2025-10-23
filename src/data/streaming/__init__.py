"""
Real-time data streaming components.

DEPRECATION NOTICE (October 2025):
-----------------------------------
LiveCandleGenerator is DEPRECATED and replaced by VALRCandlePoller.

Components:
- LiveCandleGenerator: DEPRECATED - Use VALRCandlePoller instead
  (Real-time OHLC candle generation from WebSocket trades)
  REASON: VALR NEW_TRADE WebSocket events are account-only, not public market data

NEW ARCHITECTURE:
- Primary: VALRCandlePoller (src/data/collectors/valr_candle_poller.py)
  Polls VALR REST API /buckets endpoint every 60s for 1m candles
- Supplementary: VALRWebSocketClient (src/data/collectors/valr_websocket_client.py)
  MARKET_SUMMARY_UPDATE for real-time prices (position monitoring)
"""

import warnings

# Import LiveCandleGenerator but show deprecation warning
from .live_candle_generator import LiveCandleGenerator

# Show deprecation warning when module is imported
warnings.warn(
    "LiveCandleGenerator is deprecated as of October 2025. "
    "Use VALRCandlePoller (src/data/collectors/valr_candle_poller.py) instead. "
    "Reason: VALR NEW_TRADE WebSocket events are account-only, not public market data.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = ['LiveCandleGenerator']
