"""
GARCH(1,1) Volatility Forecasting Model

Implements GARCH(1,1) volatility modeling for regime classification
and position sizing adjustments.

GARCH(1,1) variance equation:
σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁

Where:
- ω (omega): Constant term
- α (alpha): ARCH parameter (reaction to market shocks)
- β (beta): GARCH parameter (persistence of volatility)
- Stationarity constraint: α + β < 1
"""

import asyncpg
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from arch import arch_model
from arch.univariate import ConstantMean, GARCH

from config.settings import settings
from config.risk_config import (
    GARCH_CONFIG,
    REGIME_BENCHMARKS,
    DEFAULT_REGIME_BENCHMARKS
)
from src.utils.logger import get_logger
from src.risk.position_sizing.models import VolatilityForecast

logger = get_logger(__name__, component="garch_model")


class GARCHVolatilityModel:
    """
    GARCH(1,1) volatility forecasting model.

    Forecasts daily volatility and classifies market regimes.
    """

    def __init__(self):
        self.lookback_days = GARCH_CONFIG['lookback_days']
        self.min_observations = GARCH_CONFIG['min_observations']
        self.update_interval_hours = GARCH_CONFIG['update_interval_hours']
        self.extreme_move_threshold = GARCH_CONFIG['extreme_move_threshold']

    async def update_volatility_forecast(self, pair: str) -> Dict:
        """
        Update volatility forecast for a trading pair.

        Main entry point for volatility updates.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')

        Returns:
            Dict with volatility forecast and regime

        Raises:
            ValueError: If insufficient data or invalid pair
        """
        logger.info(f"Updating volatility forecast for {pair}")

        # Check if update is needed
        if not await self._should_update(pair):
            logger.info(f"Volatility forecast for {pair} is recent, skipping update")
            return await self._get_latest_forecast(pair)

        # Fetch log returns
        log_returns = await self._fetch_log_returns(pair)

        if len(log_returns) < self.min_observations:
            raise ValueError(
                f"Insufficient data for {pair}: {len(log_returns)} observations "
                f"(minimum {self.min_observations} required)"
            )

        # Fit GARCH model
        garch_params = self._fit_garch(log_returns)

        # Forecast volatility
        daily_vol = self._forecast_volatility(log_returns, garch_params)
        annual_vol = daily_vol * np.sqrt(252)  # Annualize (252 trading days)

        # Classify regime
        regime = self._classify_regime(pair, daily_vol)

        # Create forecast object
        forecast = VolatilityForecast(
            pair=pair,
            daily_volatility=float(daily_vol),
            annualized_volatility=float(annual_vol),
            volatility_regime=regime,
            garch_omega=float(garch_params['omega']),
            garch_alpha=float(garch_params['alpha']),
            garch_beta=float(garch_params['beta']),
            forecast_timestamp=datetime.utcnow()
        )

        # Save to database
        await self._save_forecast_to_db(forecast)

        logger.info(
            f"Volatility forecast updated for {pair}: "
            f"Daily={daily_vol:.4f}, Regime={regime}"
        )

        return forecast.to_dict()

    async def _should_update(self, pair: str) -> bool:
        """
        Check if volatility forecast needs updating.

        Update if:
        1. No recent forecast (> update_interval_hours old)
        2. Extreme price move detected (> extreme_move_threshold)
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            # Check last forecast timestamp
            row = await conn.fetchrow("""
                SELECT forecast_timestamp
                FROM volatility_forecasts
                WHERE pair = $1
                ORDER BY forecast_timestamp DESC
                LIMIT 1
            """, pair)

            if not row:
                return True  # No forecast exists, need to create one

            last_update = row['forecast_timestamp']
            time_since_update = datetime.utcnow() - last_update
            hours_since_update = time_since_update.total_seconds() / 3600

            if hours_since_update >= self.update_interval_hours:
                logger.info(f"Forecast for {pair} is {hours_since_update:.1f}h old, updating")
                return True

            # Check for extreme move
            if await self._detect_extreme_move(pair, conn):
                logger.warning(f"Extreme move detected for {pair}, forcing update")
                return True

            return False

        finally:
            await conn.close()

    async def _detect_extreme_move(self, pair: str, conn: asyncpg.Connection) -> bool:
        """
        Detect extreme price moves that warrant immediate volatility update.

        Checks if price has moved more than extreme_move_threshold since last update.
        """
        row = await conn.fetchrow("""
            WITH latest_price AS (
                SELECT close_price
                FROM market_ohlc
                WHERE pair = $1 AND timeframe = '5m'
                ORDER BY close_time DESC
                LIMIT 1
            ),
            price_1h_ago AS (
                SELECT close_price
                FROM market_ohlc
                WHERE pair = $1 AND timeframe = '5m'
                    AND close_time <= NOW() - INTERVAL '1 hour'
                ORDER BY close_time DESC
                LIMIT 1
            )
            SELECT
                l.close_price as current,
                h.close_price as hour_ago
            FROM latest_price l
            CROSS JOIN price_1h_ago h
        """, pair)

        if not row:
            return False

        current_price = float(row['current'])
        price_1h_ago = float(row['hour_ago'])

        if price_1h_ago == 0:
            return False

        move_pct = abs((current_price - price_1h_ago) / price_1h_ago)

        return move_pct >= self.extreme_move_threshold

    async def _fetch_log_returns(self, pair: str) -> np.ndarray:
        """
        Fetch historical log returns for GARCH fitting.

        Uses 1-minute candles to calculate log returns over lookback period.
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            cutoff_time = datetime.utcnow() - timedelta(days=self.lookback_days)

            rows = await conn.fetch("""
                SELECT close_price, close_time
                FROM market_ohlc
                WHERE pair = $1
                    AND timeframe = '1m'
                    AND close_time >= $2
                ORDER BY close_time ASC
            """, pair, cutoff_time)

            if len(rows) < self.min_observations:
                raise ValueError(
                    f"Insufficient data: {len(rows)} candles "
                    f"(need {self.min_observations})"
                )

            # Convert to prices array
            prices = np.array([float(row['close_price']) for row in rows])

            # Calculate log returns: ln(P_t / P_{t-1})
            log_returns = np.diff(np.log(prices))

            # Remove any NaN or inf values
            log_returns = log_returns[np.isfinite(log_returns)]

            return log_returns

        finally:
            await conn.close()

    def _fit_garch(self, log_returns: np.ndarray) -> Dict[str, float]:
        """
        Fit GARCH(1,1) model to log returns.

        Uses arch library for maximum likelihood estimation.

        Returns:
            Dict with omega, alpha, beta parameters
        """
        # Convert to percentage returns for better numerical stability
        returns_pct = log_returns * 100

        # Fit GARCH(1,1) model
        # ConstantMean + GARCH(1,1) is standard specification
        model = arch_model(
            returns_pct,
            mean='Constant',
            vol='GARCH',
            p=1,  # GARCH lag order
            q=1,  # ARCH lag order
            rescale=False
        )

        # Fit model (suppress optimization output)
        result = model.fit(disp='off', show_warning=False)

        # Extract parameters
        omega = result.params['omega']
        alpha = result.params['alpha[1]']
        beta = result.params['beta[1]']

        # Validate stationarity constraint
        if (alpha + beta) >= 1.0:
            logger.warning(
                f"GARCH model non-stationary: alpha={alpha:.4f}, beta={beta:.4f}, "
                f"sum={alpha+beta:.4f}. Adjusting parameters."
            )
            # Scale down to ensure stationarity
            scale_factor = 0.98 / (alpha + beta)
            alpha *= scale_factor
            beta *= scale_factor

        return {
            'omega': omega,
            'alpha': alpha,
            'beta': beta
        }

    def _forecast_volatility(
        self,
        log_returns: np.ndarray,
        garch_params: Dict[str, float]
    ) -> float:
        """
        Forecast 1-step ahead volatility using GARCH parameters.

        Uses the GARCH(1,1) variance equation:
        σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁
        """
        omega = garch_params['omega']
        alpha = garch_params['alpha']
        beta = garch_params['beta']

        # Convert to percentage returns (same scale as fitting)
        returns_pct = log_returns * 100

        # Calculate unconditional variance (long-run variance)
        # σ²_long = ω / (1 - α - β)
        unconditional_var = omega / (1.0 - alpha - beta)

        # Get last squared return (ε²ₜ₋₁)
        last_squared_return = returns_pct[-1] ** 2

        # Estimate last conditional variance using moving average
        # Use last 20 returns for better estimate
        last_conditional_var = np.var(returns_pct[-20:]) if len(returns_pct) >= 20 else unconditional_var

        # Forecast next period variance
        # σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁
        forecast_var = omega + alpha * last_squared_return + beta * last_conditional_var

        # Volatility is square root of variance
        forecast_vol = np.sqrt(forecast_var)

        # Convert back to decimal (from percentage)
        forecast_vol_decimal = forecast_vol / 100.0

        return forecast_vol_decimal

    def _classify_regime(self, pair: str, daily_volatility: float) -> str:
        """
        Classify volatility regime based on daily volatility.

        Regimes: LOW, MEDIUM, HIGH, EXTREME
        """
        # Get benchmarks for this pair
        benchmarks = REGIME_BENCHMARKS.get(pair, DEFAULT_REGIME_BENCHMARKS)

        if daily_volatility < benchmarks['low']:
            return 'LOW'
        elif daily_volatility < benchmarks['medium']:
            return 'MEDIUM'
        elif daily_volatility < benchmarks['high']:
            return 'HIGH'
        else:
            return 'EXTREME'

    async def _save_forecast_to_db(self, forecast: VolatilityForecast):
        """Save volatility forecast to database."""
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                INSERT INTO volatility_forecasts (
                    pair, daily_volatility, annualized_volatility,
                    volatility_regime, garch_omega, garch_alpha, garch_beta,
                    forecast_timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
                forecast.pair,
                forecast.daily_volatility,
                forecast.annualized_volatility,
                forecast.volatility_regime,
                forecast.garch_omega,
                forecast.garch_alpha,
                forecast.garch_beta,
                forecast.forecast_timestamp
            )

            logger.info(f"Saved volatility forecast for {forecast.pair} to database")

        finally:
            await conn.close()

    async def _get_latest_forecast(self, pair: str) -> Dict:
        """Get the most recent volatility forecast from database."""
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            row = await conn.fetchrow("""
                SELECT pair, daily_volatility, annualized_volatility,
                       volatility_regime, garch_omega, garch_alpha, garch_beta,
                       forecast_timestamp
                FROM volatility_forecasts
                WHERE pair = $1
                ORDER BY forecast_timestamp DESC
                LIMIT 1
            """, pair)

            if not row:
                raise ValueError(f"No volatility forecast found for {pair}")

            return {
                'pair': row['pair'],
                'daily_volatility': float(row['daily_volatility']),
                'annualized_volatility': float(row['annualized_volatility']),
                'volatility_regime': row['volatility_regime'],
                'garch_omega': float(row['garch_omega']),
                'garch_alpha': float(row['garch_alpha']),
                'garch_beta': float(row['garch_beta']),
                'forecast_timestamp': row['forecast_timestamp'].isoformat()
            }

        finally:
            await conn.close()
