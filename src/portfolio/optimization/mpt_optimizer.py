"""
src/portfolio/optimization/mpt_optimizer.py

Modern Portfolio Theory optimization with Black-Litterman model.

Helios V3.0 - Tier 5: Guardian Portfolio Manager
Phase 5, Week 22: Modern Portfolio Theory Optimizer
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy.optimize import minimize
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class MPTOptimizer:
    """
    Modern Portfolio Theory optimizer.

    Uses Black-Litterman model to combine:
    - Market equilibrium (prior) - derived from market cap weights
    - ML predictions (investor views) - from neural network predictions
    - Covariance matrix (risk model) - from historical returns

    Outputs optimal portfolio weights that maximize Sharpe ratio.
    """

    def __init__(self, db_session: AsyncSession, risk_free_rate: float = 0.05):
        """
        Initialize MPT Optimizer.

        Args:
            db_session: Database session for queries
            risk_free_rate: Annual risk-free rate (default: 5%)
        """
        self.db = db_session
        self.risk_free_rate = risk_free_rate
        logger.info(f"MPTOptimizer initialized with risk_free_rate={risk_free_rate:.2%}")

    async def calculate_optimal_weights(
        self,
        pairs: List[str],
        ml_predictions: Dict[str, float],  # pair -> expected return
        confidence_scores: Dict[str, float]  # pair -> confidence (0-1)
    ) -> Dict[str, float]:
        """
        Calculate optimal portfolio weights using Black-Litterman.

        5-Step Process:
        1. Calculate covariance matrix from historical returns
        2. Get market cap weights (equilibrium prior)
        3. Calculate implied equilibrium returns (reverse optimization)
        4. Apply Black-Litterman to incorporate ML views
        5. Optimize for maximum Sharpe ratio

        Args:
            pairs: List of trading pairs (e.g., ['BTCZAR', 'ETHZAR', 'SOLZAR'])
            ml_predictions: Expected returns from ML (e.g., {'BTCZAR': 0.05})
            confidence_scores: Confidence in each prediction (0-1)

        Returns:
            Optimal weights dict (e.g., {'BTCZAR': 0.35, 'ETHZAR': 0.40, 'SOLZAR': 0.25})
        """
        logger.info(f"Calculating optimal weights for {len(pairs)} pairs")

        # Step 1: Calculate covariance matrix
        cov_matrix = await self._calculate_covariance_matrix(pairs)
        logger.debug(f"Covariance matrix shape: {cov_matrix.shape}")

        # Step 2: Get market cap weights (equilibrium prior)
        market_weights = await self._get_market_cap_weights(pairs)
        logger.debug(f"Market weights: {dict(zip(pairs, market_weights))}")

        # Step 3: Calculate implied equilibrium returns (reverse optimization)
        risk_aversion = 2.5  # Typical risk aversion coefficient
        implied_returns = risk_aversion * cov_matrix @ market_weights
        logger.debug(f"Implied returns: {dict(zip(pairs, implied_returns))}")

        # Step 4: Apply Black-Litterman to incorporate ML views
        posterior_returns, posterior_cov = self._black_litterman(
            prior_returns=implied_returns,
            prior_cov=cov_matrix,
            views=ml_predictions,
            view_confidence=confidence_scores,
            pairs=pairs
        )
        logger.debug(f"Posterior returns: {dict(zip(pairs, posterior_returns))}")

        # Step 5: Optimize for maximum Sharpe ratio
        optimal_weights = self._optimize_sharpe_ratio(
            expected_returns=posterior_returns,
            cov_matrix=posterior_cov
        )
        logger.info(f"Optimal weights: {dict(zip(pairs, optimal_weights))}")

        # Convert to dict
        return {pairs[i]: float(optimal_weights[i]) for i in range(len(pairs))}

    async def _calculate_covariance_matrix(self, pairs: List[str]) -> np.ndarray:
        """
        Calculate 90-day covariance matrix of returns.

        Uses daily returns from market_ohlc table to build covariance matrix.

        Args:
            pairs: List of trading pairs

        Returns:
            Covariance matrix as numpy array (n x n)
        """
        logger.debug(f"Calculating covariance matrix for {pairs}")

        # Fetch returns for all pairs
        returns_data = {}
        for pair in pairs:
            query = text("""
                SELECT close_time, close_price / LAG(close_price) OVER (ORDER BY close_time) - 1 as return
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '1d'
                    AND close_time >= NOW() - INTERVAL '90 days'
                ORDER BY close_time
            """)

            result = await self.db.execute(query, {'pair': pair})
            rows = result.fetchall()

            returns = [float(r[1]) for r in rows if r[1] is not None]
            returns_data[pair] = returns

        # Check if we have enough data
        min_data_points = min(len(v) for v in returns_data.values()) if returns_data else 0
        if min_data_points < 30:
            logger.warning(f"Insufficient data for covariance matrix: {min_data_points} days (need 30+)")
            # Return identity matrix as fallback
            n = len(pairs)
            return np.eye(n) * 0.01  # Small variance

        # Convert to DataFrame
        df = pd.DataFrame(returns_data)

        # Calculate covariance matrix
        cov_matrix = df.cov().values

        return cov_matrix

    async def _get_market_cap_weights(self, pairs: List[str]) -> np.ndarray:
        """
        Get market cap weights as equilibrium prior.

        For crypto, uses trading volume as proxy for market cap.

        Args:
            pairs: List of trading pairs

        Returns:
            Market cap weights as numpy array (sums to 1.0)
        """
        logger.debug(f"Calculating market cap weights for {pairs}")

        volumes = {}
        for pair in pairs:
            query = text("""
                SELECT AVG(volume) as avg_volume
                FROM market_ohlc
                WHERE pair = :pair
                    AND timeframe = '1d'
                    AND close_time >= NOW() - INTERVAL '30 days'
            """)

            result = await self.db.execute(query, {'pair': pair})
            row = result.fetchone()

            volumes[pair] = float(row[0]) if row and row[0] else 1.0

        # Normalize to weights
        total_volume = sum(volumes.values())
        if total_volume == 0:
            # Equal weights if no volume data
            weights = np.ones(len(pairs)) / len(pairs)
        else:
            weights = np.array([volumes[pair] / total_volume for pair in pairs])

        return weights

    def _black_litterman(
        self,
        prior_returns: np.ndarray,
        prior_cov: np.ndarray,
        views: Dict[str, float],
        view_confidence: Dict[str, float],
        pairs: List[str]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Black-Litterman model: Combine prior with ML views.

        Formula:
        posterior_returns = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ [(τΣ)⁻¹π + P'Ω⁻¹Q]

        Where:
        - π = prior (implied equilibrium returns)
        - Σ = covariance matrix
        - τ = uncertainty in prior (typically 0.025)
        - P = pick matrix (which assets have views)
        - Q = view vector (ML predicted returns)
        - Ω = uncertainty in views (diagonal matrix, 1/confidence)

        Args:
            prior_returns: Implied equilibrium returns
            prior_cov: Covariance matrix
            views: ML predictions (expected returns)
            view_confidence: Confidence in each prediction (0-1)
            pairs: List of trading pairs

        Returns:
            Tuple of (posterior_returns, posterior_cov)
        """
        n = len(pairs)
        tau = 0.025  # Uncertainty in prior

        # Build pick matrix P (identity for absolute views)
        P = np.eye(n)

        # Build view vector Q (ML predictions)
        Q = np.array([views.get(pair, 0.0) for pair in pairs])

        # Build view uncertainty Ω (higher confidence = lower uncertainty)
        omega_diag = [1.0 / max(view_confidence.get(pair, 0.5), 0.1) for pair in pairs]
        Omega = np.diag(omega_diag)

        # Calculate posterior
        tau_sigma = tau * prior_cov

        try:
            tau_sigma_inv = np.linalg.inv(tau_sigma)
        except np.linalg.LinAlgError:
            logger.warning("Singular tau_sigma matrix, using pseudoinverse")
            tau_sigma_inv = np.linalg.pinv(tau_sigma)

        try:
            omega_inv = np.linalg.inv(Omega)
        except np.linalg.LinAlgError:
            logger.warning("Singular Omega matrix, using pseudoinverse")
            omega_inv = np.linalg.pinv(Omega)

        P_omega_inv = P.T @ omega_inv

        posterior_precision = tau_sigma_inv + P_omega_inv @ P

        try:
            posterior_cov = np.linalg.inv(posterior_precision)
        except np.linalg.LinAlgError:
            logger.warning("Singular posterior_precision, using pseudoinverse")
            posterior_cov = np.linalg.pinv(posterior_precision)

        posterior_returns = posterior_cov @ (
            tau_sigma_inv @ prior_returns + P_omega_inv @ Q
        )

        return posterior_returns, posterior_cov

    def _optimize_sharpe_ratio(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Optimize portfolio weights for maximum Sharpe ratio.

        Sharpe Ratio = (E[R] - Rf) / σ

        Constraints:
        - Weights sum to 1
        - All weights >= 0 (long-only)
        - Max weight per asset: 0.40 (40%)

        Args:
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix

        Returns:
            Optimal weights as numpy array
        """
        n = len(expected_returns)

        # Objective: minimize negative Sharpe ratio
        def neg_sharpe(weights):
            portfolio_return = weights @ expected_returns
            portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)

            # Avoid division by zero
            if portfolio_vol < 1e-10:
                return 1e10

            return -(portfolio_return - self.risk_free_rate) / portfolio_vol

        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # weights sum to 1
        ]

        # Bounds: 0 <= weight <= 0.40
        bounds = [(0.0, 0.40) for _ in range(n)]

        # Initial guess: equal weights
        w0 = np.ones(n) / n

        # Optimize
        try:
            result = minimize(
                neg_sharpe,
                w0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000}
            )

            if not result.success:
                logger.warning(f"Optimization failed: {result.message}, using equal weights")
                return np.ones(n) / n

            return result.x

        except Exception as e:
            logger.error(f"Optimization error: {e}, using equal weights")
            return np.ones(n) / n

    async def calculate_portfolio_metrics(
        self,
        weights: Dict[str, float],
        expected_returns: Dict[str, float]
    ) -> Dict:
        """
        Calculate portfolio metrics (return, volatility, Sharpe).

        Args:
            weights: Portfolio weights (e.g., {'BTCZAR': 0.35})
            expected_returns: Expected returns (e.g., {'BTCZAR': 0.05})

        Returns:
            Dict with expected_return_annual, volatility_annual, sharpe_ratio, weights
        """
        pairs = list(weights.keys())

        # Get covariance matrix
        cov_matrix = await self._calculate_covariance_matrix(pairs)

        # Convert to arrays
        w = np.array([weights[pair] for pair in pairs])
        r = np.array([expected_returns[pair] for pair in pairs])

        # Calculate metrics
        portfolio_return = w @ r
        portfolio_vol = np.sqrt(w @ cov_matrix @ w)

        # Avoid division by zero
        if portfolio_vol < 1e-10:
            sharpe_ratio = 0.0
        else:
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol

        return {
            'expected_return_annual': float(portfolio_return),
            'volatility_annual': float(portfolio_vol),
            'sharpe_ratio': float(sharpe_ratio),
            'weights': weights
        }
