"""
src/portfolio/risk/portfolio_risk_manager.py

Portfolio-level risk management and limit enforcement.

Helios V3.0 - Tier 5: Guardian Portfolio Manager
Phase 5, Week 21: Portfolio Risk Manager
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class PortfolioRiskLimits:
    """
    Portfolio risk limits configuration.

    These limits enforce institutional-grade risk management at the portfolio level.
    All trades must pass these checks before execution.
    """
    max_drawdown_pct: float = 0.15  # -15% max drawdown (hard stop)
    max_single_position_pct: float = 0.20  # 20% max per position
    max_sector_exposure_pct: float = 0.60  # 60% max in one sector (e.g., crypto)
    max_correlation_threshold: float = 0.90  # Don't add position if corr > 0.90
    daily_loss_limit_pct: float = 0.05  # -5% daily loss limit
    max_leverage: float = 3.0  # 3x max portfolio leverage

    # Dynamic position capacity (calculated based on risk, not hardcoded count)
    max_portfolio_risk_exposure_pct: float = 0.15  # Max 15% of portfolio at risk
    min_position_size_pct: float = 0.05  # Minimum 5% position size to be worthwhile


@dataclass
class RiskCheckResult:
    """
    Result of portfolio risk check.

    Contains all information about whether a trade passed risk checks
    and detailed reasons for any failures.
    """
    passed: bool  # True if all checks passed
    reason: str  # Human-readable reason (empty if passed, violations if failed)
    current_metrics: Dict  # Current portfolio metrics
    violated_limits: List[str]  # List of specific limit violations


class PortfolioRiskManager:
    """
    Portfolio-level risk management.

    Responsibilities:
    - Check portfolio risk limits before trades
    - Monitor aggregate portfolio risk
    - Enforce position size limits
    - Check correlation exposure
    - Track daily loss limits

    This is the final guardian before any trade execution.
    All 7 risk checks must pass for a trade to be approved.
    """

    def __init__(self, db_session: AsyncSession, limits: Optional[PortfolioRiskLimits] = None):
        """
        Initialize Portfolio Risk Manager.

        Args:
            db_session: Database session for queries
            limits: Optional custom risk limits (uses defaults if None)
        """
        self.db = db_session
        self.limits = limits or PortfolioRiskLimits()
        logger.info(f"PortfolioRiskManager initialized with limits: "
                   f"max_drawdown={self.limits.max_drawdown_pct:.1%}, "
                   f"max_position={self.limits.max_single_position_pct:.1%}, "
                   f"max_leverage={self.limits.max_leverage:.1f}x, "
                   f"max_portfolio_risk=DYNAMIC (3%-30% via volatility targeting, Moreira & Muir 2017)")

    async def check_trade_risk(
        self,
        pair: str,
        signal: str,
        trade_params: Dict
    ) -> RiskCheckResult:
        """
        Check if proposed trade violates portfolio risk limits.

        Runs all 7 risk checks:
        1. Portfolio drawdown limit
        2. Daily loss limit
        3. Dynamic position capacity (risk-based, not hardcoded count)
        4. Single position size
        5. Sector exposure
        6. Correlation exposure
        7. Portfolio leverage

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: Trade signal ('BUY' or 'SELL')
            trade_params: Dict with position_size_zar, leverage, etc.

        Returns:
            RiskCheckResult with passed=True/False and detailed reasons
        """
        violated_limits = []
        current_metrics = await self._get_portfolio_metrics()

        # CHECK 1: Drawdown limit
        if current_metrics['current_drawdown_pct'] > self.limits.max_drawdown_pct:
            violated_limits.append(
                f"Portfolio drawdown {current_metrics['current_drawdown_pct']:.2%} "
                f"exceeds limit {self.limits.max_drawdown_pct:.2%}"
            )
            logger.warning(f"Risk check failed: Drawdown limit exceeded for {pair}")

        # CHECK 2: Daily loss limit
        if current_metrics['daily_pnl_pct'] < -self.limits.daily_loss_limit_pct:
            violated_limits.append(
                f"Daily loss {current_metrics['daily_pnl_pct']:.2%} "
                f"exceeds limit {self.limits.daily_loss_limit_pct:.2%}"
            )
            logger.warning(f"Risk check failed: Daily loss limit exceeded for {pair}")

        # CHECK 3: Dynamic position capacity based on risk
        capacity_check = await self._check_position_capacity(trade_params, current_metrics)
        if not capacity_check['has_capacity']:
            violated_limits.append(capacity_check['reason'])
            logger.warning(f"Risk check failed: {capacity_check['reason']} for {pair}")

        # CHECK 4: Single position size
        position_size_pct = trade_params['position_size_zar'] / current_metrics['total_value_zar']
        if position_size_pct > self.limits.max_single_position_pct:
            violated_limits.append(
                f"Position size {position_size_pct:.2%} exceeds limit "
                f"{self.limits.max_single_position_pct:.2%}"
            )
            logger.warning(f"Risk check failed: Position size too large for {pair}")

        # CHECK 5: Sector exposure (all crypto = one sector for now)
        sector_exposure = await self._calculate_sector_exposure(pair, trade_params)
        if sector_exposure > self.limits.max_sector_exposure_pct:
            violated_limits.append(
                f"Sector exposure {sector_exposure:.2%} exceeds limit "
                f"{self.limits.max_sector_exposure_pct:.2%}"
            )
            logger.warning(f"Risk check failed: Sector exposure too high for {pair}")

        # CHECK 6: Correlation exposure
        corr_check = await self._check_correlation_exposure(pair, trade_params)
        if not corr_check['passed']:
            violated_limits.append(corr_check['reason'])
            logger.warning(f"Risk check failed: High correlation for {pair}")

        # CHECK 7: Portfolio leverage
        portfolio_leverage = await self._calculate_portfolio_leverage(trade_params)
        if portfolio_leverage > self.limits.max_leverage:
            violated_limits.append(
                f"Portfolio leverage {portfolio_leverage:.1f}x exceeds limit "
                f"{self.limits.max_leverage:.1f}x"
            )
            logger.warning(f"Risk check failed: Leverage too high for {pair}")

        # Determine overall result
        passed = len(violated_limits) == 0

        if passed:
            logger.info(f"All risk checks passed for {pair} {signal} trade")
        else:
            logger.warning(f"Risk checks failed for {pair}: {len(violated_limits)} violations")

        return RiskCheckResult(
            passed=passed,
            reason='; '.join(violated_limits) if violated_limits else 'All risk checks passed',
            current_metrics=current_metrics,
            violated_limits=violated_limits
        )

    async def _get_portfolio_metrics(self) -> Dict:
        """
        Get current portfolio metrics.

        Queries the portfolio_state table for current values and calculates
        additional metrics like daily P&L and open position count.

        Returns:
            Dict with total_value_zar, peak_value_zar, current_drawdown_pct,
            daily_pnl_pct, num_open_positions
        """
        query = text("""
            SELECT
                total_value_zar,
                peak_value_zar,
                current_drawdown_pct,
                last_updated
            FROM portfolio_state
            WHERE id = 1
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        if not row:
            # Default values if no portfolio state exists
            logger.warning("No portfolio_state found, using default values")
            return {
                'total_value_zar': 100000.0,
                'peak_value_zar': 100000.0,
                'current_drawdown_pct': 0.0,
                'daily_pnl_pct': 0.0,
                'num_open_positions': 0
            }

        # Get daily P&L
        daily_pnl = await self._get_daily_pnl()

        # Count open positions
        count_query = text("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'")
        count_result = await self.db.execute(count_query)
        num_open = count_result.scalar() or 0

        return {
            'total_value_zar': float(row[0]),
            'peak_value_zar': float(row[1]),
            'current_drawdown_pct': float(row[2]),
            'daily_pnl_pct': daily_pnl,
            'num_open_positions': num_open
        }

    async def _check_position_capacity(self, trade_params: Dict, current_metrics: Dict) -> Dict:
        """
        Check if there's capacity for a new position based on risk exposure.

        Instead of a hardcoded position count limit, this calculates dynamic capacity
        based on:
        1. Current risk exposure vs max allowed (15% of portfolio)
        2. Available capital
        3. Minimum position size requirements

        Args:
            trade_params: Proposed trade parameters with position_size_zar, stop_loss_pct, etc.
            current_metrics: Current portfolio metrics

        Returns:
            Dict with 'has_capacity' (bool), 'reason' (str), and 'metrics' (dict)
        """
        portfolio_value = current_metrics['total_value_zar']

        # Calculate current total risk exposure (sum of all position risks)
        risk_query = text("""
            SELECT
                SUM(
                    position_value_zar *
                    CASE
                        WHEN signal = 'BUY' THEN (entry_price - stop_loss_price) / entry_price
                        WHEN signal = 'SELL' THEN (stop_loss_price - entry_price) / entry_price
                        ELSE 0
                    END
                ) as total_risk_zar
            FROM positions
            WHERE status = 'OPEN'
                AND stop_loss_price IS NOT NULL
        """)

        result = await self.db.execute(risk_query)
        row = result.fetchone()
        current_risk_zar = float(row[0]) if row and row[0] else 0.0
        current_risk_pct = current_risk_zar / portfolio_value if portfolio_value > 0 else 0.0

        # Calculate risk of proposed trade
        if 'stop_loss_pct' in trade_params and trade_params['stop_loss_pct']:
            proposed_risk_zar = trade_params['position_size_zar'] * abs(trade_params['stop_loss_pct'])
        else:
            # If no stop loss, assume 2% risk (typical)
            proposed_risk_zar = trade_params['position_size_zar'] * 0.02

        # Total risk if this trade is added
        total_risk_after = current_risk_zar + proposed_risk_zar
        total_risk_pct_after = total_risk_after / portfolio_value if portfolio_value > 0 else 0.0

        # Check if adding this trade would exceed max risk exposure
        # Use dynamic volatility targeting instead of static limit (Moreira & Muir, 2017)
        max_risk_pct = await self.get_max_portfolio_risk_pct()
        if total_risk_pct_after > max_risk_pct:
            available_risk_zar = (max_risk_pct * portfolio_value) - current_risk_zar
            return {
                'has_capacity': False,
                'reason': (f"Insufficient risk capacity: Adding this trade would put portfolio at "
                          f"{total_risk_pct_after:.2%} risk (max {max_risk_pct:.2%}). "
                          f"Current risk: {current_risk_pct:.2%}, "
                          f"Available capacity: R{available_risk_zar:,.2f}"),
                'metrics': {
                    'current_risk_pct': current_risk_pct,
                    'proposed_risk_pct': proposed_risk_zar / portfolio_value,
                    'total_risk_pct_after': total_risk_pct_after,
                    'max_risk_pct': max_risk_pct,
                    'available_risk_zar': available_risk_zar
                }
            }

        # Check if we have sufficient capital
        cash_query = text("SELECT cash_balance_zar FROM portfolio_state WHERE id = 1")
        cash_result = await self.db.execute(cash_query)
        cash_row = cash_result.fetchone()
        cash_balance = float(cash_row[0]) if cash_row and cash_row[0] else 0.0

        if trade_params['position_size_zar'] > cash_balance:
            return {
                'has_capacity': False,
                'reason': (f"Insufficient capital: Trade requires R{trade_params['position_size_zar']:,.2f}, "
                          f"only R{cash_balance:,.2f} available"),
                'metrics': {
                    'cash_balance': cash_balance,
                    'required': trade_params['position_size_zar']
                }
            }

        # Check if position is too small to be worthwhile
        position_size_pct = trade_params['position_size_zar'] / portfolio_value
        if position_size_pct < self.limits.min_position_size_pct:
            return {
                'has_capacity': False,
                'reason': (f"Position too small: {position_size_pct:.2%} of portfolio "
                          f"(minimum {self.limits.min_position_size_pct:.2%})"),
                'metrics': {
                    'position_size_pct': position_size_pct,
                    'min_position_size_pct': self.limits.min_position_size_pct
                }
            }

        # All checks passed - we have capacity
        remaining_capacity_zar = (max_risk_pct * portfolio_value) - total_risk_after
        return {
            'has_capacity': True,
            'reason': 'Sufficient risk capacity and capital available',
            'metrics': {
                'current_risk_pct': current_risk_pct,
                'proposed_risk_pct': proposed_risk_zar / portfolio_value,
                'total_risk_pct_after': total_risk_pct_after,
                'max_risk_pct': max_risk_pct,
                'remaining_capacity_zar': remaining_capacity_zar,
                'cash_balance': cash_balance,
                'num_open_positions': current_metrics['num_open_positions']
            }
        }

    async def _get_daily_pnl(self) -> float:
        """
        Calculate today's P&L as percentage.

        Compares current portfolio value to value at start of today.

        Returns:
            Daily P&L as decimal (e.g., -0.05 for -5%)
        """
        query = text("""
            WITH today_start AS (
                SELECT total_value_zar
                FROM portfolio_snapshots
                WHERE snapshot_time >= CURRENT_DATE
                ORDER BY snapshot_time ASC
                LIMIT 1
            ),
            current_value AS (
                SELECT total_value_zar
                FROM portfolio_state
                WHERE id = 1
            )
            SELECT
                (c.total_value_zar - t.total_value_zar) / t.total_value_zar as daily_return
            FROM current_value c
            CROSS JOIN today_start t
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        return float(row[0]) if row and row[0] is not None else 0.0

    async def _calculate_sector_exposure(self, new_pair: str, trade_params: Dict) -> float:
        """
        Calculate sector exposure if this trade is added.

        For crypto trading, all pairs (BTCZAR, ETHZAR, SOLZAR) are considered
        one sector. Future enhancement: split by asset class, market cap, etc.

        Args:
            new_pair: Trading pair for new position
            trade_params: Trade parameters with position_size_zar

        Returns:
            Sector exposure as decimal (e.g., 0.60 for 60%)
        """
        # Get current sector exposure (all crypto positions)
        query = text("""
            SELECT SUM(position_value_zar) as total_crypto
            FROM positions
            WHERE status = 'OPEN'
                AND pair IN ('BTCZAR', 'ETHZAR', 'SOLZAR')
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        current_crypto_value = float(row[0]) if row and row[0] else 0.0

        # Add new position
        new_crypto_value = current_crypto_value + trade_params['position_size_zar']

        # Get portfolio value
        portfolio_query = text("SELECT total_value_zar FROM portfolio_state WHERE id = 1")
        portfolio_result = await self.db.execute(portfolio_query)
        portfolio_row = portfolio_result.fetchone()
        portfolio_value = float(portfolio_row[0]) if portfolio_row else 100000.0

        return new_crypto_value / portfolio_value

    async def _check_correlation_exposure(self, new_pair: str, trade_params: Dict) -> Dict:
        """
        Check if adding this position creates excessive correlation risk.

        Calculates correlation between new pair and all existing open positions.
        Rejects if any correlation exceeds threshold (default 0.90).

        Args:
            new_pair: Trading pair for new position
            trade_params: Trade parameters

        Returns:
            Dict with 'passed' (bool) and 'reason' (str)
        """
        # Get all open positions
        query = text("""
            SELECT p.pair, p.position_value_zar
            FROM positions p
            WHERE p.status = 'OPEN'
        """)

        result = await self.db.execute(query)
        rows = result.fetchall()

        if not rows:
            return {'passed': True, 'reason': ''}

        # Check correlation with each existing position
        for row in rows:
            existing_pair = row[0]
            existing_value = float(row[1])

            # Skip if same pair (correlation would be 1.0)
            if existing_pair == new_pair:
                continue

            # Get correlation between pairs
            corr = await self._get_pair_correlation(new_pair, existing_pair)

            if corr > self.limits.max_correlation_threshold:
                return {
                    'passed': False,
                    'reason': f"High correlation ({corr:.2f}) with existing position {existing_pair}"
                }

        return {'passed': True, 'reason': ''}

    async def _get_pair_correlation(self, pair1: str, pair2: str) -> float:
        """
        Get 30-day rolling correlation between two pairs.

        Uses PostgreSQL's CORR() aggregate function on daily returns.

        Args:
            pair1: First trading pair
            pair2: Second trading pair

        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        query = text("""
            WITH pair1_returns AS (
                SELECT
                    close_time,
                    CASE
                        WHEN LAG(close_price) OVER (ORDER BY close_time) > 0
                        THEN (close_price / LAG(close_price) OVER (ORDER BY close_time)) - 1
                        ELSE NULL
                    END as return
                FROM market_ohlc
                WHERE pair = :pair1 AND timeframe = '1d'
                    AND close_time >= NOW() - INTERVAL '30 days'
                    AND close_price > 0
                ORDER BY close_time
            ),
            pair2_returns AS (
                SELECT
                    close_time,
                    CASE
                        WHEN LAG(close_price) OVER (ORDER BY close_time) > 0
                        THEN (close_price / LAG(close_price) OVER (ORDER BY close_time)) - 1
                        ELSE NULL
                    END as return
                FROM market_ohlc
                WHERE pair = :pair2 AND timeframe = '1d'
                    AND close_time >= NOW() - INTERVAL '30 days'
                    AND close_price > 0
                ORDER BY close_time
            )
            SELECT CORR(p1.return, p2.return) as correlation
            FROM pair1_returns p1
            JOIN pair2_returns p2 ON p1.close_time = p2.close_time
            WHERE p1.return IS NOT NULL AND p2.return IS NOT NULL
        """)

        result = await self.db.execute(query, {'pair1': pair1, 'pair2': pair2})
        row = result.fetchone()

        return float(row[0]) if row and row[0] is not None else 0.0

    async def _calculate_portfolio_leverage(self, new_trade_params: Dict) -> float:
        """
        Calculate portfolio leverage if this trade is added.

        Portfolio leverage = Total leveraged exposure / Portfolio value

        Args:
            new_trade_params: Trade parameters with position_size_zar and leverage

        Returns:
            Portfolio leverage ratio (e.g., 2.5 for 2.5x leverage)
        """
        # Get current leveraged exposure
        query = text("""
            SELECT SUM(position_value_zar * leverage) as total_exposure
            FROM positions
            WHERE status = 'OPEN'
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        current_exposure = float(row[0]) if row and row[0] else 0.0

        # Add new position exposure
        new_exposure = current_exposure + (
            new_trade_params['position_size_zar'] * new_trade_params['leverage']
        )

        # Get portfolio value
        portfolio_query = text("SELECT total_value_zar FROM portfolio_state WHERE id = 1")
        portfolio_result = await self.db.execute(portfolio_query)
        portfolio_row = portfolio_result.fetchone()
        portfolio_value = float(portfolio_row[0]) if portfolio_row else 100000.0

        return new_exposure / portfolio_value

    async def _get_portfolio_volatility(self) -> float:
        """
        Calculate current portfolio volatility using recent price data.

        Uses 30-day rolling volatility of portfolio returns (annualized).
        Falls back to Bitcoin volatility if insufficient portfolio history.

        Returns:
            Daily volatility as decimal (e.g., 0.015 for 1.5% daily volatility)
        """
        # Try to get portfolio volatility from recent snapshots
        query = text("""
            WITH portfolio_returns AS (
                SELECT
                    snapshot_time,
                    CASE
                        WHEN LAG(total_value_zar) OVER (ORDER BY snapshot_time) > 0
                        THEN (total_value_zar / LAG(total_value_zar) OVER (ORDER BY snapshot_time)) - 1
                        ELSE NULL
                    END as return
                FROM portfolio_snapshots
                WHERE snapshot_time >= NOW() - INTERVAL '30 days'
                    AND total_value_zar > 0
                ORDER BY snapshot_time
            )
            SELECT STDDEV(return) as volatility
            FROM portfolio_returns
            WHERE return IS NOT NULL
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        if row and row[0] is not None and row[0] > 0:
            # Convert to daily volatility (already in daily frequency from snapshots)
            portfolio_vol = float(row[0])
            logger.debug(f"Portfolio volatility from historical returns: {portfolio_vol:.4f}")
            return portfolio_vol

        # Fallback: Use BTC volatility as proxy (dominant crypto asset)
        btc_query = text("""
            WITH btc_returns AS (
                SELECT
                    close_time,
                    CASE
                        WHEN LAG(close_price) OVER (ORDER BY close_time) > 0
                        THEN (close_price / LAG(close_price) OVER (ORDER BY close_time)) - 1
                        ELSE NULL
                    END as return
                FROM market_ohlc
                WHERE pair = 'BTCZAR'
                    AND timeframe = '1d'
                    AND close_time >= NOW() - INTERVAL '30 days'
                    AND close_price > 0
                ORDER BY close_time
            )
            SELECT STDDEV(return) as volatility
            FROM btc_returns
            WHERE return IS NOT NULL
        """)

        btc_result = await self.db.execute(btc_query)
        btc_row = btc_result.fetchone()

        if btc_row and btc_row[0] is not None and btc_row[0] > 0:
            btc_vol = float(btc_row[0])
            logger.debug(f"Using BTC volatility as proxy: {btc_vol:.4f}")
            return btc_vol

        # Ultimate fallback: Use typical crypto volatility (1.5% daily)
        logger.warning("No historical volatility data available, using default 1.5% daily")
        return 0.015

    async def get_max_portfolio_risk_pct(self) -> float:
        """
        Get dynamic portfolio risk limit - AGGRESSIVE APPROACH.

        High volatility = MORE OPPORTUNITY = Higher risk limits
        Low volatility = BORING MARKETS = Lower risk limits

        Returns:
            Dynamic portfolio risk limit as decimal (e.g., 0.35 for 35%)
        """
        # Get current portfolio volatility forecast
        forecast_vol = await self._get_portfolio_volatility()

        # AGGRESSIVE PARAMETERS - Trade volatility as opportunity
        # Higher vol = more price movement = more profit potential = take more risk
        min_risk = 0.25  # Minimum 25% even in calm markets
        max_risk = 0.50  # Maximum 50% in high volatility markets

        # Scale risk UP with volatility (opposite of institutional approach)
        # Normal crypto vol ~2%, aggressive vol ~4%+
        # Linear scaling: risk increases as volatility increases
        if forecast_vol < 0.015:  # Low vol (<1.5% daily)
            dynamic_risk = min_risk  # 25% in boring markets
        elif forecast_vol > 0.03:  # High vol (>3% daily)
            dynamic_risk = max_risk  # 50% in volatile markets
        else:
            # Linear interpolation between min and max
            vol_ratio = (forecast_vol - 0.015) / (0.03 - 0.015)
            dynamic_risk = min_risk + (vol_ratio * (max_risk - min_risk))

        logger.info(
            f"AGGRESSIVE risk limit: {dynamic_risk:.2%} "
            f"(forecast vol: {forecast_vol:.2%}, regime: "
            f"{'HIGH VOL' if forecast_vol > 0.025 else 'NORMAL' if forecast_vol > 0.015 else 'LOW VOL'})"
        )

        return dynamic_risk
