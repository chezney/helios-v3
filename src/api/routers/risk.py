"""
Risk Management API Endpoints

Provides comprehensive risk management:
- Risk configuration (limits, thresholds, position sizing)
- Real-time risk monitoring (VaR, drawdown, exposure)
- GARCH volatility forecasting
- Correlation analysis
- Risk score calculation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import asyncpg
import numpy as np

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="risk_api")

router = APIRouter(prefix="/api/risk", tags=["Risk Management"])


# Models

class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_total_exposure_pct: float = Field(95.0, ge=0, le=100, description="Max total exposure as % of portfolio")
    max_position_size_pct: float = Field(20.0, ge=0, le=100, description="Max single position size as % of portfolio")
    max_leverage: float = Field(1.0, ge=1.0, le=10.0, description="Maximum leverage allowed")
    max_drawdown_threshold_pct: float = Field(15.0, ge=0, le=100, description="Max acceptable drawdown %")
    max_daily_loss_zar: float = Field(10000.0, ge=0, description="Max daily loss in ZAR")
    max_concurrent_positions: int = Field(5, ge=1, le=20, description="Max concurrent open positions")

    # Position sizing
    use_kelly_criterion: bool = Field(True, description="Use Kelly Criterion for position sizing")
    kelly_fraction: float = Field(0.25, ge=0.1, le=1.0, description="Kelly fraction (0.25 = quarter Kelly)")
    use_volatility_sizing: bool = Field(True, description="Adjust size based on volatility")
    atr_multiplier: float = Field(2.0, ge=1.0, le=5.0, description="ATR multiplier for stops")

    # Stop-loss
    default_stop_loss_pct: float = Field(2.0, ge=0.5, le=10.0, description="Default stop-loss %")
    use_trailing_stop: bool = Field(False, description="Enable trailing stops")
    trailing_stop_distance_pct: float = Field(1.5, ge=0.5, le=5.0, description="Trailing stop distance %")

    # Risk score thresholds
    low_risk_threshold: float = Field(0.3, ge=0, le=1, description="Low risk upper bound")
    medium_risk_threshold: float = Field(0.6, ge=0, le=1, description="Medium risk upper bound")
    high_risk_threshold: float = Field(0.8, ge=0, le=1, description="High risk upper bound")
    block_trades_above_score: float = Field(0.85, ge=0, le=1, description="Block trades above this risk score")


class RiskDashboard(BaseModel):
    """Real-time risk dashboard metrics."""
    timestamp: datetime

    # Portfolio risk
    current_risk_score: float = Field(..., ge=0, le=1, description="Current portfolio risk score")
    portfolio_exposure_pct: float = Field(..., description="Current exposure as % of portfolio")
    current_leverage: float = Field(..., description="Current leverage ratio")
    current_drawdown_pct: float = Field(..., description="Current drawdown from peak")
    max_drawdown_pct: float = Field(..., description="Maximum historical drawdown")

    # Dynamic risk targeting (Moreira & Muir, 2017)
    dynamic_portfolio_risk_limit_pct: float = Field(..., description="Dynamic portfolio risk limit (3-30%)")
    portfolio_volatility_daily_pct: float = Field(..., description="Current daily portfolio volatility")
    risk_regime: str = Field(..., description="Risk regime: AGGRESSIVE, NORMAL, DEFENSIVE, MAXIMUM_PROTECTION")

    # Value at Risk
    var_95_zar: float = Field(..., description="Value at Risk (95% confidence)")
    var_99_zar: float = Field(..., description="Value at Risk (99% confidence)")
    cvar_95_zar: float = Field(..., description="Conditional VaR (95%)")

    # Position metrics
    num_open_positions: int
    largest_position_pct: float = Field(..., description="Largest position as % of portfolio")
    concentration_score: float = Field(..., ge=0, le=1, description="Position concentration score")

    # Daily metrics
    daily_pnl_zar: float
    daily_loss_limit_remaining_zar: float
    trades_today: int


class VaRCalculation(BaseModel):
    """Value at Risk calculation result."""
    symbol: Optional[str] = None
    confidence_level: float = Field(..., description="Confidence level (e.g., 0.95, 0.99)")
    time_horizon_days: int = Field(1, description="Time horizon in days")
    var_zar: float = Field(..., description="Value at Risk in ZAR")
    cvar_zar: Optional[float] = Field(None, description="Conditional VaR in ZAR")
    method: str = Field(..., description="Calculation method (historical, parametric, monte_carlo)")
    calculated_at: datetime


class CorrelationMatrix(BaseModel):
    """Asset correlation matrix."""
    symbols: List[str]
    correlation_matrix: List[List[float]]
    timestamp: datetime
    lookback_days: int


class GARCHForecast(BaseModel):
    """GARCH volatility forecast."""
    symbol: str
    current_volatility: float = Field(..., description="Current volatility (annualized)")
    forecasted_volatility: List[float] = Field(..., description="Next N periods volatility forecast")
    forecast_horizon_hours: int
    confidence_interval_95: Dict[str, List[float]] = Field(..., description="95% confidence interval")
    timestamp: datetime


# Global risk config (in production, use database)
_risk_config = RiskConfig()


# Database connection helper

async def get_db_connection():
    """Create database connection."""
    return await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
    )


# Helper functions

async def calculate_portfolio_risk_score() -> float:
    """Calculate current portfolio risk score (0.0-1.0)."""
    conn = await get_db_connection()
    try:
        # Get portfolio state
        portfolio = await conn.fetchrow("""
            SELECT total_value_zar, current_drawdown_pct
            FROM portfolio_state
            ORDER BY last_updated DESC
            LIMIT 1
        """)

        if not portfolio:
            return 0.5  # Default medium risk

        # Get open positions
        positions = await conn.fetch("""
            SELECT quantity, entry_price
            FROM positions
            WHERE status = 'OPEN'
        """)

        # Calculate risk factors
        drawdown_risk = min(float(portfolio['current_drawdown_pct']) / 15.0, 1.0)  # 15% max
        exposure_risk = len(positions) / 10.0  # Normalize to 10 positions

        # Combine into overall score
        risk_score = (drawdown_risk * 0.6 + exposure_risk * 0.4)

        return min(max(risk_score, 0.0), 1.0)

    finally:
        await conn.close()


async def calculate_dynamic_portfolio_risk_limit() -> tuple[float, float, str]:
    """
    Calculate dynamic portfolio risk limit - AGGRESSIVE APPROACH.

    High volatility = MORE OPPORTUNITY = Higher risk limits
    Low volatility = BORING MARKETS = Lower risk limits

    Returns:
        Tuple of (dynamic_risk_limit, portfolio_volatility, risk_regime)
    """
    conn = await get_db_connection()
    try:
        # Calculate portfolio volatility from recent returns (30-day rolling)
        portfolio_vol_query = """
            WITH portfolio_returns AS (
                SELECT
                    snapshot_time,
                    total_value_zar / LAG(total_value_zar) OVER (ORDER BY snapshot_time) - 1 as return
                FROM portfolio_snapshots
                WHERE snapshot_time >= NOW() - INTERVAL '30 days'
                ORDER BY snapshot_time
            )
            SELECT STDDEV(return) as volatility
            FROM portfolio_returns
            WHERE return IS NOT NULL
        """

        result = await conn.fetchrow(portfolio_vol_query)

        if result and result['volatility'] is not None and result['volatility'] > 0:
            portfolio_vol = float(result['volatility'])
        else:
            # Fallback: Use BTC volatility as proxy
            btc_query = """
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
            """

            btc_result = await conn.fetchrow(btc_query)

            if btc_result and btc_result['volatility'] is not None and btc_result['volatility'] > 0:
                portfolio_vol = float(btc_result['volatility'])
            else:
                # Ultimate fallback: Use typical crypto volatility (1.5% daily)
                portfolio_vol = 0.015

        # AGGRESSIVE PARAMETERS - Trade volatility as opportunity
        # Higher vol = more price movement = more profit potential = take more risk
        min_risk = 0.25  # Minimum 25% even in calm markets
        max_risk = 0.50  # Maximum 50% in high volatility markets

        # Scale risk UP with volatility (opposite of institutional approach)
        # Normal crypto vol ~2%, aggressive vol ~4%+
        # Linear scaling: risk increases as volatility increases
        if portfolio_vol < 0.015:  # Low vol (<1.5% daily)
            dynamic_risk = min_risk  # 25% in boring markets
        elif portfolio_vol > 0.03:  # High vol (>3% daily)
            dynamic_risk = max_risk  # 50% in volatile markets
        else:
            # Linear interpolation between min and max
            vol_ratio = (portfolio_vol - 0.015) / (0.03 - 0.015)
            dynamic_risk = min_risk + (vol_ratio * (max_risk - min_risk))

        # Determine risk regime (based on AGGRESSIVE scaling)
        if dynamic_risk >= 0.45:
            risk_regime = "AGGRESSIVE"
        elif dynamic_risk >= 0.35:
            risk_regime = "NORMAL"
        elif dynamic_risk >= 0.25:
            risk_regime = "DEFENSIVE"
        else:
            risk_regime = "MAXIMUM_PROTECTION"

        logger.info(
            f"AGGRESSIVE risk limit: {dynamic_risk:.2%} "
            f"(forecast vol: {portfolio_vol:.2%}, regime: {risk_regime})"
        )

        return (dynamic_risk, portfolio_vol, risk_regime)

    finally:
        await conn.close()


async def calculate_var(confidence_level: float = 0.95, time_horizon_days: int = 1) -> VaRCalculation:
    """Calculate Value at Risk using historical method."""
    conn = await get_db_connection()
    try:
        # Get recent position P&Ls
        lookback_date = datetime.utcnow() - timedelta(days=90)

        pnls = await conn.fetch("""
            SELECT pnl_zar
            FROM positions
            WHERE status = 'CLOSED'
                AND exit_time >= $1
                AND pnl_zar IS NOT NULL
            ORDER BY exit_time DESC
        """, lookback_date)

        if len(pnls) < 30:
            # Not enough data, use conservative estimate
            return VaRCalculation(
                confidence_level=confidence_level,
                time_horizon_days=time_horizon_days,
                var_zar=5000.0,  # Conservative estimate
                method="historical (insufficient data)",
                calculated_at=datetime.utcnow()
            )

        # Calculate VaR
        returns = np.array([float(p['pnl_zar']) for p in pnls])
        var_percentile = (1 - confidence_level) * 100
        var_zar = abs(np.percentile(returns, var_percentile))

        # Calculate CVaR (average of losses beyond VaR)
        losses = returns[returns < -var_zar]
        cvar_zar = abs(np.mean(losses)) if len(losses) > 0 else var_zar

        # Adjust for time horizon (simple sqrt(t) rule)
        var_zar *= np.sqrt(time_horizon_days)
        cvar_zar *= np.sqrt(time_horizon_days)

        return VaRCalculation(
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days,
            var_zar=float(var_zar),
            cvar_zar=float(cvar_zar),
            method="historical",
            calculated_at=datetime.utcnow()
        )

    finally:
        await conn.close()


# Endpoints

@router.get("/config", response_model=RiskConfig)
async def get_risk_config():
    """
    Get current risk management configuration.

    Returns all risk parameters including:
    - Position size limits
    - Exposure limits
    - Stop-loss settings
    - Risk score thresholds
    """
    return _risk_config


@router.post("/config")
async def update_risk_config(config: RiskConfig):
    """
    Update risk management configuration.

    **Warning**: Changes affect all future trades immediately.
    """
    global _risk_config

    old_config = _risk_config
    _risk_config = config

    logger.warning(f"Risk configuration updated. Max position size: {config.max_position_size_pct}%")

    return {
        "success": True,
        "message": "Risk configuration updated",
        "previous_max_position_size_pct": old_config.max_position_size_pct,
        "new_max_position_size_pct": config.max_position_size_pct,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/dashboard", response_model=RiskDashboard)
async def get_risk_dashboard():
    """
    Get real-time risk monitoring dashboard.

    Returns comprehensive risk metrics including:
    - Current risk score
    - Exposure and leverage
    - Drawdown metrics
    - Value at Risk (VaR)
    - Position concentration
    - Daily P&L and limits
    """
    conn = await get_db_connection()
    try:
        # Get portfolio state
        portfolio = await conn.fetchrow("""
            SELECT
                total_value_zar,
                current_drawdown_pct,
                max_drawdown_pct,
                daily_pnl_zar
            FROM portfolio_state
            ORDER BY last_updated DESC
            LIMIT 1
        """)

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not initialized")

        # Get open positions
        positions = await conn.fetch("""
            SELECT quantity, entry_price, pair
            FROM positions
            WHERE status = 'OPEN'
        """)

        # Calculate exposure
        portfolio_value = float(portfolio['total_value_zar'])
        total_position_value = sum(float(p['quantity']) * float(p['entry_price']) for p in positions)
        exposure_pct = (total_position_value / portfolio_value * 100) if portfolio_value > 0 else 0

        # Calculate largest position
        if positions:
            position_sizes = [float(p['quantity']) * float(p['entry_price']) for p in positions]
            largest_position = max(position_sizes)
            largest_position_pct = (largest_position / portfolio_value * 100)

            # Concentration score (Herfindahl index)
            weights = [size / total_position_value for size in position_sizes]
            concentration = sum(w * w for w in weights)  # 0-1, higher = more concentrated
        else:
            largest_position_pct = 0.0
            concentration = 0.0

        # Get today's trades
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM positions
            WHERE entry_time >= $1
        """, today)

        # Calculate VaR
        var_calc = await calculate_var(confidence_level=0.95)
        var_99 = await calculate_var(confidence_level=0.99)

        # Calculate risk score
        risk_score = await calculate_portfolio_risk_score()

        # Calculate dynamic portfolio risk limit (Moreira & Muir, 2017)
        dynamic_risk_limit, portfolio_vol, risk_regime = await calculate_dynamic_portfolio_risk_limit()

        # Daily loss limit
        daily_pnl = float(portfolio['daily_pnl_zar']) if portfolio['daily_pnl_zar'] else 0.0
        max_daily_loss = _risk_config.max_daily_loss_zar
        daily_loss_remaining = max_daily_loss + daily_pnl  # Positive if within limit

        return RiskDashboard(
            timestamp=datetime.utcnow(),
            current_risk_score=risk_score,
            portfolio_exposure_pct=exposure_pct,
            current_leverage=1.0,  # Spot trading, no leverage
            current_drawdown_pct=float(portfolio['current_drawdown_pct']),
            max_drawdown_pct=float(portfolio['max_drawdown_pct']),
            dynamic_portfolio_risk_limit_pct=dynamic_risk_limit * 100,  # Convert to percentage
            portfolio_volatility_daily_pct=portfolio_vol * 100,  # Convert to percentage
            risk_regime=risk_regime,
            var_95_zar=var_calc.var_zar,
            var_99_zar=var_99.var_zar,
            cvar_95_zar=var_calc.cvar_zar or var_calc.var_zar,
            num_open_positions=len(positions),
            largest_position_pct=largest_position_pct,
            concentration_score=concentration,
            daily_pnl_zar=daily_pnl,
            daily_loss_limit_remaining_zar=daily_loss_remaining,
            trades_today=trades_today or 0
        )

    finally:
        await conn.close()


@router.get("/var", response_model=VaRCalculation)
async def get_value_at_risk(
    confidence_level: float = 0.95,
    time_horizon_days: int = 1
):
    """
    Calculate Value at Risk (VaR).

    Args:
        confidence_level: Confidence level (0.95 for 95%, 0.99 for 99%)
        time_horizon_days: Time horizon in days (default 1)

    Returns VaR estimation using historical method.
    """
    if confidence_level <= 0 or confidence_level >= 1:
        raise HTTPException(status_code=400, detail="Confidence level must be between 0 and 1")

    if time_horizon_days < 1 or time_horizon_days > 30:
        raise HTTPException(status_code=400, detail="Time horizon must be between 1 and 30 days")

    return await calculate_var(confidence_level, time_horizon_days)


@router.get("/correlation", response_model=CorrelationMatrix)
async def get_correlation_matrix(
    symbols: Optional[str] = None,
    lookback_days: int = 30
):
    """
    Get correlation matrix for portfolio assets.

    Args:
        symbols: Comma-separated list of symbols (default: all open positions)
        lookback_days: Lookback period in days (default 30)

    Returns correlation matrix showing how assets move together.
    """
    conn = await get_db_connection()
    try:
        # Determine which symbols to analyze
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
        else:
            # Get symbols from open positions
            rows = await conn.fetch("""
                SELECT DISTINCT pair
                FROM positions
                WHERE status = 'OPEN'
            """)
            symbol_list = [row['pair'] for row in rows]

        if len(symbol_list) < 2:
            # Need at least 2 symbols for correlation
            return CorrelationMatrix(
                symbols=symbol_list,
                correlation_matrix=[[1.0]],
                timestamp=datetime.utcnow(),
                lookback_days=lookback_days
            )

        # Fetch price data for each symbol
        lookback_date = datetime.utcnow() - timedelta(days=lookback_days)

        returns_data = {}
        for symbol in symbol_list:
            prices = await conn.fetch("""
                SELECT close, timestamp
                FROM candles_1h
                WHERE pair = $1 AND timestamp >= $2
                ORDER BY timestamp ASC
            """, symbol, lookback_date)

            if len(prices) > 1:
                # Calculate returns
                price_array = np.array([float(p['close']) for p in prices])
                returns = np.diff(price_array) / price_array[:-1]
                returns_data[symbol] = returns

        # Calculate correlation matrix
        if len(returns_data) >= 2:
            # Ensure all return series have same length (use minimum)
            min_length = min(len(r) for r in returns_data.values())
            aligned_returns = {k: v[:min_length] for k, v in returns_data.items()}

            # Create return matrix
            symbols_sorted = sorted(aligned_returns.keys())
            return_matrix = np.array([aligned_returns[s] for s in symbols_sorted])

            # Calculate correlation
            corr_matrix = np.corrcoef(return_matrix)

            return CorrelationMatrix(
                symbols=symbols_sorted,
                correlation_matrix=corr_matrix.tolist(),
                timestamp=datetime.utcnow(),
                lookback_days=lookback_days
            )
        else:
            # Not enough data, return identity matrix
            n = len(symbol_list)
            identity = np.eye(n).tolist()

            return CorrelationMatrix(
                symbols=symbol_list,
                correlation_matrix=identity,
                timestamp=datetime.utcnow(),
                lookback_days=lookback_days
            )

    finally:
        await conn.close()


@router.get("/garch/{symbol}", response_model=GARCHForecast)
async def get_garch_forecast(
    symbol: str,
    forecast_hours: int = 24
):
    """
    Get GARCH volatility forecast for a symbol.

    Args:
        symbol: Trading pair symbol
        forecast_hours: Forecast horizon in hours (default 24)

    Returns GARCH(1,1) volatility forecast with confidence intervals.

    **Note**: This is a simplified implementation. Production would use
    proper GARCH model fitting from arch library.
    """
    conn = await get_db_connection()
    try:
        # Fetch historical prices
        try:
            lookback_date = datetime.utcnow() - timedelta(days=90)

            prices = await conn.fetch("""
                SELECT close, timestamp
                FROM candles_1h
                WHERE pair = $1 AND timestamp >= $2
                ORDER BY timestamp DESC
                LIMIT 720
            """, symbol, lookback_date)
        except Exception as e:
            # Check if table doesn't exist
            if "does not exist" in str(e):
                raise HTTPException(
                    status_code=500,
                    detail=f"GARCH forecast unavailable: candles_1h table not found"
                )
            raise

        if len(prices) < 100:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for {symbol} GARCH forecast (need 100 points, have {len(prices)})"
            )

        # Calculate returns
        price_array = np.array([float(p['close']) for p in reversed(prices)])
        returns = np.diff(np.log(price_array))

        # Calculate current volatility (simple std of recent returns)
        current_vol = np.std(returns[-24:]) * np.sqrt(365 * 24)  # Annualized

        # Simplified GARCH forecast (constant volatility)
        # Production: Use arch library for proper GARCH(1,1) fitting
        forecast = [current_vol] * min(forecast_hours, 168)  # Max 1 week

        # Simple confidence intervals (±1.96 * std)
        std_error = current_vol * 0.1  # Approximate
        upper_bound = [v + 1.96 * std_error for v in forecast]
        lower_bound = [v - 1.96 * std_error for v in forecast]

        return GARCHForecast(
            symbol=symbol,
            current_volatility=float(current_vol),
            forecasted_volatility=forecast,
            forecast_horizon_hours=len(forecast),
            confidence_interval_95={
                "upper": upper_bound,
                "lower": lower_bound
            },
            timestamp=datetime.utcnow()
        )

    finally:
        await conn.close()


@router.get("/limits")
async def get_risk_limits():
    """Get current risk limit statuses and remaining capacity."""
    conn = await get_db_connection()
    try:
        # Get portfolio
        portfolio = await conn.fetchrow("""
            SELECT total_value_zar, current_drawdown_pct
            FROM portfolio_state
            ORDER BY last_updated DESC
            LIMIT 1
        """)

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not initialized")

        # Get positions
        positions = await conn.fetch("""
            SELECT * FROM positions WHERE status = 'OPEN'
        """)

        portfolio_value = float(portfolio['total_value_zar'])

        # Calculate current exposure
        total_exposure = sum(float(p['quantity']) * float(p['entry_price']) for p in positions)
        exposure_pct = (total_exposure / portfolio_value * 100) if portfolio_value > 0 else 0

        return {
            "max_exposure": {
                "limit_pct": _risk_config.max_total_exposure_pct,
                "current_pct": exposure_pct,
                "remaining_pct": _risk_config.max_total_exposure_pct - exposure_pct,
                "status": "OK" if exposure_pct < _risk_config.max_total_exposure_pct else "EXCEEDED"
            },
            "max_positions": {
                "limit": _risk_config.max_concurrent_positions,
                "current": len(positions),
                "remaining": _risk_config.max_concurrent_positions - len(positions),
                "status": "OK" if len(positions) < _risk_config.max_concurrent_positions else "EXCEEDED"
            },
            "max_drawdown": {
                "limit_pct": _risk_config.max_drawdown_threshold_pct,
                "current_pct": float(portfolio['current_drawdown_pct']),
                "remaining_pct": _risk_config.max_drawdown_threshold_pct - float(portfolio['current_drawdown_pct']),
                "status": "OK" if float(portfolio['current_drawdown_pct']) < _risk_config.max_drawdown_threshold_pct else "EXCEEDED"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        await conn.close()
