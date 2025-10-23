"""
Market Context Aggregator for LLM Strategic Analysis

Aggregates market data across multiple dimensions:
- Price action (24h, 7d, 30d changes)
- Cross-asset correlations
- Market microstructure (orderbook, spread, depth)
- Regime detection (trend, volatility, liquidity)
- Recent ML predictions performance
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import numpy as np
import pandas as pd


class MarketContextAggregator:
    """
    Aggregate market context for LLM strategic analysis.

    Collects:
    - Recent price action (multi-timeframe)
    - Cross-asset correlations
    - Market microstructure (orderbook, volume)
    - Regime classifications
    - Recent ML performance
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize market context aggregator.

        Args:
            db_session: AsyncPG database session
        """
        self.db = db_session

    async def build_context(self, pair: str) -> Dict:
        """
        Build complete market context for a trading pair.

        Returns structured dict ready for LLM prompt.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')

        Returns:
            Dict with complete market context including price action,
            correlations, regimes, and ML performance
        """
        context = {
            'timestamp': datetime.utcnow().isoformat(),
            'pair': pair,
            'price_action': await self._get_price_action(pair),
            'correlations': await self._get_correlations(pair),
            'microstructure': await self._get_microstructure(pair),
            'volatility_regime': await self._get_volatility_regime(pair),
            'trend_regime': await self._detect_trend_regime(pair),
            'liquidity_regime': await self._detect_liquidity_regime(pair),
            'recent_ml_predictions': await self._get_recent_predictions(pair),
        }

        return context

    async def _get_price_action(self, pair: str) -> Dict:
        """
        Get recent price action across multiple timeframes.

        Fetches current price and calculates percentage changes
        over 24h, 7d, and 30d periods.

        Args:
            pair: Trading pair

        Returns:
            Dict with current price and multi-timeframe changes
        """
        query = text("""
            WITH current_price AS (
                SELECT close_price as price
                FROM market_ohlc
                WHERE pair = :pair AND timeframe = '5m'
                ORDER BY close_time DESC
                LIMIT 1
            ),
            price_24h_ago AS (
                SELECT close_price as price
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '5m'
                    AND close_time <= NOW() - INTERVAL '24 hours'
                ORDER BY close_time DESC
                LIMIT 1
            ),
            price_7d_ago AS (
                SELECT close_price as price
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '5m'
                    AND close_time <= NOW() - INTERVAL '7 days'
                ORDER BY close_time DESC
                LIMIT 1
            ),
            price_30d_ago AS (
                SELECT close_price as price
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '5m'
                    AND close_time <= NOW() - INTERVAL '30 days'
                ORDER BY close_time DESC
                LIMIT 1
            )
            SELECT
                c.price as current_price,
                h24.price as price_24h_ago,
                d7.price as price_7d_ago,
                d30.price as price_30d_ago
            FROM current_price c
            CROSS JOIN price_24h_ago h24
            CROSS JOIN price_7d_ago d7
            CROSS JOIN price_30d_ago d30
        """)

        result = await self.db.execute(query, {'pair': pair})
        row = result.fetchone()

        if not row:
            return {'error': 'Insufficient price data'}

        current = float(row[0])
        price_24h = float(row[1]) if row[1] else current
        price_7d = float(row[2]) if row[2] else current
        price_30d = float(row[3]) if row[3] else current

        return {
            'current_price': current,
            'change_24h_pct': ((current - price_24h) / price_24h) * 100 if price_24h else 0.0,
            'change_7d_pct': ((current - price_7d) / price_7d) * 100 if price_7d else 0.0,
            'change_30d_pct': ((current - price_30d) / price_30d) * 100 if price_30d else 0.0,
            'price_24h_ago': price_24h,
            'price_7d_ago': price_7d,
            'price_30d_ago': price_30d,
        }

    async def _get_correlations(self, pair: str) -> Dict:
        """
        Calculate cross-asset correlations (30-day rolling).

        Computes correlation matrix between major trading pairs
        and classifies the correlation regime.

        Args:
            pair: Trading pair

        Returns:
            Dict with correlations and regime classification
        """
        # Get 30 days of daily returns for all pairs
        query = text("""
            SELECT pair, close_time, close_price
            FROM market_ohlc
            WHERE timeframe = '1d'
                AND close_time >= NOW() - INTERVAL '30 days'
                AND pair IN ('BTCZAR', 'ETHZAR', 'SOLZAR')
            ORDER BY pair, close_time ASC
        """)

        result = await self.db.execute(query)
        rows = result.fetchall()

        if len(rows) < 30:
            return {
                'correlations': {},
                'correlation_regime': 'UNKNOWN',
                'error': 'Insufficient data for correlation'
            }

        # Convert to pandas DataFrame
        df = pd.DataFrame(rows, columns=['pair', 'time', 'price'])
        df['price'] = df['price'].astype(float)

        # Pivot to wide format
        try:
            pivot = df.pivot(index='time', columns='pair', values='price')

            # Calculate returns
            returns = pivot.pct_change().dropna()

            if len(returns) < 10:
                return {
                    'correlations': {},
                    'correlation_regime': 'UNKNOWN',
                    'error': 'Insufficient returns data'
                }

            # Calculate correlation matrix
            corr_matrix = returns.corr()

            # Extract correlations for the target pair
            correlations = {}
            if pair in corr_matrix.columns:
                for other_pair in corr_matrix.columns:
                    if other_pair != pair:
                        correlations[other_pair] = float(corr_matrix.loc[pair, other_pair])

            return {
                'correlations': correlations,
                'correlation_regime': self._classify_correlation_regime(correlations)
            }
        except Exception as e:
            return {
                'correlations': {},
                'correlation_regime': 'UNKNOWN',
                'error': f'Correlation calculation failed: {str(e)}'
            }

    def _classify_correlation_regime(self, correlations: Dict[str, float]) -> str:
        """
        Classify correlation regime based on average correlation.

        Args:
            correlations: Dict of pair correlations

        Returns:
            'CRISIS' (>0.8), 'COUPLED' (>0.5), or 'DECOUPLED' (<0.5)
        """
        if not correlations:
            return 'UNKNOWN'

        avg_corr = np.mean(list(correlations.values()))

        if avg_corr > 0.8:
            return 'CRISIS'  # Everything moving together
        elif avg_corr > 0.5:
            return 'COUPLED'  # Normal crypto correlation
        else:
            return 'DECOUPLED'  # Independent movements

    async def _get_microstructure(self, pair: str) -> Dict:
        """
        Get current market microstructure from latest orderbook snapshot.

        Analyzes orderbook to determine spread, depth, and imbalance.

        Args:
            pair: Trading pair

        Returns:
            Dict with spread, depth, and imbalance metrics
        """
        query = text("""
            SELECT bids, asks, bid_ask_spread, market_depth_10
            FROM orderbook_snapshots
            WHERE pair = :pair
            ORDER BY snapshot_time DESC
            LIMIT 1
        """)

        result = await self.db.execute(query, {'pair': pair})
        row = result.fetchone()

        if not row:
            return {
                'bid_ask_spread_pct': 0.0,
                'market_depth_10_levels': 0.0,
                'orderbook_imbalance': 0.0,
                'error': 'No orderbook data'
            }

        bids = row[0]  # JSONB
        asks = row[1]  # JSONB
        spread = float(row[2]) if row[2] else 0.0
        depth = float(row[3]) if row[3] else 0.0

        return {
            'bid_ask_spread_pct': spread,
            'market_depth_10_levels': depth,
            'orderbook_imbalance': self._calculate_imbalance(bids, asks)
        }

    def _calculate_imbalance(self, bids: List, asks: List) -> float:
        """
        Calculate orderbook imbalance (positive = more buy pressure).

        Args:
            bids: List of bid orders
            asks: List of ask orders

        Returns:
            Imbalance ratio between -1 and 1
        """
        if not bids or not asks:
            return 0.0

        try:
            # Sum top 10 levels
            bid_volume = sum(float(b.get('quantity', 0)) for b in bids[:10])
            ask_volume = sum(float(a.get('quantity', 0)) for a in asks[:10])

            total = bid_volume + ask_volume
            if total == 0:
                return 0.0

            return (bid_volume - ask_volume) / total
        except Exception:
            return 0.0

    async def _get_volatility_regime(self, pair: str) -> str:
        """
        Get current volatility regime from Tier 3 forecasts.

        Args:
            pair: Trading pair

        Returns:
            'LOW', 'MEDIUM', 'HIGH', 'EXTREME', or 'UNKNOWN'
        """
        query = text("""
            SELECT volatility_regime
            FROM volatility_forecasts
            WHERE pair = :pair
            ORDER BY forecast_timestamp DESC
            LIMIT 1
        """)

        result = await self.db.execute(query, {'pair': pair})
        row = result.fetchone()

        return row[0] if row else 'UNKNOWN'

    async def _detect_trend_regime(self, pair: str) -> str:
        """
        Detect trend regime using 20-period and 50-period SMAs.

        Classification:
        - BULLISH: price > SMA20 > SMA50
        - BEARISH: price < SMA20 < SMA50
        - SIDEWAYS: otherwise

        Args:
            pair: Trading pair

        Returns:
            'BULLISH', 'BEARISH', 'SIDEWAYS', or 'UNKNOWN'
        """
        query = text("""
            SELECT close_price
            FROM market_ohlc
            WHERE pair = :pair AND timeframe = '1d'
            ORDER BY close_time DESC
            LIMIT 50
        """)

        result = await self.db.execute(query, {'pair': pair})
        rows = result.fetchall()

        if len(rows) < 50:
            return 'UNKNOWN'

        prices = [float(r[0]) for r in rows][::-1]  # Reverse to chronological
        current_price = prices[-1]

        sma_20 = np.mean(prices[-20:])
        sma_50 = np.mean(prices[-50:])

        if current_price > sma_20 > sma_50:
            return 'BULLISH'
        elif current_price < sma_20 < sma_50:
            return 'BEARISH'
        else:
            return 'SIDEWAYS'

    async def _detect_liquidity_regime(self, pair: str) -> str:
        """
        Detect liquidity regime from recent volume.

        Compares current volume to 30-day average:
        - DEEP: >1.5x average
        - NORMAL: 0.5x - 1.5x average
        - THIN: <0.5x average

        Args:
            pair: Trading pair

        Returns:
            'DEEP', 'NORMAL', 'THIN', or 'UNKNOWN'
        """
        query = text("""
            WITH recent_volume AS (
                SELECT volume
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '5m'
                    AND close_time >= NOW() - INTERVAL '24 hours'
                ORDER BY close_time DESC
                LIMIT 1
            ),
            avg_volume AS (
                SELECT AVG(volume) as avg_vol
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '5m'
                    AND close_time >= NOW() - INTERVAL '30 days'
            )
            SELECT r.volume, a.avg_vol
            FROM recent_volume r
            CROSS JOIN avg_volume a
        """)

        result = await self.db.execute(query, {'pair': pair})
        row = result.fetchone()

        if not row or row[1] is None:
            return 'UNKNOWN'

        current_volume = float(row[0])
        avg_volume = float(row[1])

        if avg_volume == 0:
            return 'UNKNOWN'

        volume_ratio = current_volume / avg_volume

        if volume_ratio > 1.5:
            return 'DEEP'
        elif volume_ratio < 0.5:
            return 'THIN'
        else:
            return 'NORMAL'

    async def _get_recent_predictions(self, pair: str) -> List[Dict]:
        """
        Get last 10 ML predictions for context.

        Includes prediction accuracy for LLM to assess ML performance.

        Args:
            pair: Trading pair

        Returns:
            List of recent predictions with outcomes
        """
        query = text("""
            SELECT prediction, confidence_score, created_at, correct
            FROM ml_predictions
            WHERE pair = :pair
            ORDER BY created_at DESC
            LIMIT 10
        """)

        result = await self.db.execute(query, {'pair': pair})
        rows = result.fetchall()

        predictions = []
        for row in rows:
            predictions.append({
                'prediction': row[0],
                'confidence': float(row[1]),
                'timestamp': row[2].isoformat() if row[2] else None,
                'correct': row[3]
            })

        return predictions
