"""
Tier 3 API Router - Risk Management & Position Sizing

Endpoints for Aether Risk Engine, GARCH volatility, and position sizing.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import asyncpg
from datetime import datetime, timedelta

from config.settings import settings
from src.utils.logger import get_logger
from src.risk.aether_engine import get_aether_engine
from src.risk.portfolio_state import PortfolioStateManager

logger = get_logger(__name__, component="tier3_api")

router = APIRouter(prefix="/api/tier3", tags=["Tier 3 - Risk Management"])


@router.get("/health")
async def health_check():
    """
    Check if Tier 3 Aether Risk Engine is healthy.

    Returns:
        Health status
    """
    aether = get_aether_engine()

    if not aether:
        return {
            "status": "unavailable",
            "message": "Aether Risk Engine not initialized",
            "components": {
                "garch_model": False,
                "kelly_sizer": False,
                "leverage_calculator": False,
                "portfolio_manager": False
            }
        }

    return {
        "status": "healthy",
        "message": "Tier 3 Aether Risk Engine operational",
        "components": {
            "garch_model": True,
            "kelly_sizer": True,
            "leverage_calculator": True,
            "portfolio_manager": True
        }
    }


@router.post("/calculate-trade/{pair}")
async def calculate_trade_parameters(
    pair: str,
    signal: str = Query(..., description="Trading signal: BUY or SELL"),
    confidence: float = Query(..., ge=0.0, le=1.0, description="ML prediction confidence"),
    max_probability: Optional[float] = Query(None, ge=0.0, le=1.0, description="Max probability")
):
    """
    Calculate complete trade parameters for a ML prediction.

    Uses Aether Risk Engine to combine:
    - GARCH volatility forecast
    - Kelly position sizing
    - Dynamic leverage calculation

    Args:
        pair: Trading pair (e.g., BTCZAR)
        signal: Trading signal (BUY or SELL)
        confidence: ML prediction confidence (0.0 to 1.0)
        max_probability: Maximum probability from ML prediction

    Returns:
        Complete trade parameters including position size, leverage, SL, TP
    """
    aether = get_aether_engine()

    if not aether:
        raise HTTPException(
            status_code=503,
            detail="Aether Risk Engine not available"
        )

    # Validate signal
    if signal not in ['BUY', 'SELL', 'HOLD']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid signal: {signal}. Must be BUY, SELL, or HOLD"
        )

    try:
        result = await aether.calculate_trade_parameters(
            pair=pair.upper(),
            signal=signal.upper(),
            confidence=confidence,
            max_probability=max_probability
        )

        if result is None:
            return {
                "pair": pair.upper(),
                "signal": signal.upper(),
                "confidence": confidence,
                "trade_approved": False,
                "reason": "Signal is HOLD or confidence below minimum threshold (55%)"
            }

        return {
            "pair": result.pair,
            "signal": result.signal,
            "confidence": result.confidence,
            "trade_approved": True,
            "position_parameters": {
                "position_size_zar": result.position_size_zar,
                "leverage": result.leverage,
                "stop_loss_pct": result.stop_loss_pct,
                "take_profit_pct": result.take_profit_pct,
                "max_hold_time_hours": result.max_hold_time_hours
            },
            "kelly_metrics": {
                "kelly_fraction": result.kelly_fraction,
                "fractional_kelly": result.fractional_kelly,
                "volatility_adjusted_fraction": result.volatility_adjusted_fraction
            },
            "market_conditions": {
                "daily_volatility": result.daily_volatility,
                "volatility_regime": result.volatility_regime,
                "portfolio_value_zar": result.portfolio_value_zar,
                "current_drawdown_pct": result.current_drawdown_pct
            },
            "timestamp": result.timestamp.isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Trade parameter calculation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate trade parameters")


@router.get("/volatility/latest/{pair}")
async def get_latest_volatility(pair: str):
    """
    Get the latest GARCH volatility forecast for a pair.

    Args:
        pair: Trading pair (e.g., BTCZAR)

    Returns:
        Latest volatility forecast with regime classification
    """
    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
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
        """, pair.upper())

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No volatility forecast found for {pair}"
            )

        return {
            "pair": row['pair'],
            "daily_volatility": float(row['daily_volatility']),
            "annualized_volatility": float(row['annualized_volatility']),
            "volatility_regime": row['volatility_regime'],
            "garch_parameters": {
                "omega": float(row['garch_omega']),
                "alpha": float(row['garch_alpha']),
                "beta": float(row['garch_beta']),
                "is_stationary": (float(row['garch_alpha']) + float(row['garch_beta'])) < 1.0
            },
            "forecast_timestamp": row['forecast_timestamp'].isoformat()
        }

    finally:
        await conn.close()


@router.get("/volatility/history/{pair}")
async def get_volatility_history(
    pair: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history (max 7 days)")
):
    """
    Get volatility forecast history for a pair.

    Args:
        pair: Trading pair
        hours: Hours of history to retrieve

    Returns:
        List of volatility forecasts
    """
    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
    )

    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        rows = await conn.fetch("""
            SELECT pair, daily_volatility, annualized_volatility,
                   volatility_regime, forecast_timestamp
            FROM volatility_forecasts
            WHERE pair = $1 AND forecast_timestamp >= $2
            ORDER BY forecast_timestamp DESC
        """, pair.upper(), cutoff_time)

        forecasts = []
        for row in rows:
            forecasts.append({
                "pair": row['pair'],
                "daily_volatility": float(row['daily_volatility']),
                "annualized_volatility": float(row['annualized_volatility']),
                "volatility_regime": row['volatility_regime'],
                "forecast_timestamp": row['forecast_timestamp'].isoformat()
            })

        return {
            "pair": pair.upper(),
            "period_hours": hours,
            "forecasts": forecasts,
            "count": len(forecasts)
        }

    finally:
        await conn.close()


@router.get("/risk-decisions/recent")
async def get_recent_risk_decisions(
    limit: int = Query(20, ge=1, le=100, description="Number of decisions"),
    pair: Optional[str] = Query(None, description="Filter by trading pair")
):
    """
    Get recent Aether risk decisions.

    Args:
        limit: Number of decisions to return
        pair: Optional pair filter

    Returns:
        List of recent risk decisions
    """
    aether = get_aether_engine()

    if not aether:
        raise HTTPException(
            status_code=503,
            detail="Aether Risk Engine not available"
        )

    try:
        decisions = await aether.get_recent_risk_decisions(
            limit=limit,
            pair=pair.upper() if pair else None
        )

        return {
            "decisions": decisions,
            "count": len(decisions),
            "pair_filter": pair.upper() if pair else None
        }

    except Exception as e:
        logger.error(f"Failed to get risk decisions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve risk decisions")


@router.get("/portfolio/state")
async def get_portfolio_state():
    """
    Get current portfolio state.

    Returns:
        Portfolio value, peak value, and drawdown metrics
    """
    portfolio_manager = PortfolioStateManager()

    try:
        state = await portfolio_manager.get_portfolio_state()

        return {
            "total_value_zar": state['total_value_zar'],
            "peak_value_zar": state['peak_value_zar'],
            "current_drawdown_pct": state['current_drawdown_pct'],
            "max_drawdown_pct": state['max_drawdown_pct'],
            "profit_loss_zar": state['total_value_zar'] - 100000.0,  # Assuming 100k start
            "profit_loss_pct": ((state['total_value_zar'] - 100000.0) / 100000.0) * 100
        }

    except Exception as e:
        logger.error(f"Failed to get portfolio state: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve portfolio state")


@router.get("/regime/statistics")
async def get_regime_statistics(
    days: int = Query(7, ge=1, le=30, description="Days of history")
):
    """
    Get volatility regime statistics over a time period.

    Args:
        days: Number of days to analyze

    Returns:
        Regime distribution statistics
    """
    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
    )

    try:
        cutoff_time = datetime.utcnow() - timedelta(days=days)

        rows = await conn.fetch("""
            SELECT
                volatility_regime,
                COUNT(*) as count,
                AVG(daily_volatility) as avg_volatility,
                MAX(daily_volatility) as max_volatility,
                MIN(daily_volatility) as min_volatility
            FROM volatility_forecasts
            WHERE forecast_timestamp >= $1
            GROUP BY volatility_regime
            ORDER BY
                CASE volatility_regime
                    WHEN 'LOW' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'HIGH' THEN 3
                    WHEN 'EXTREME' THEN 4
                END
        """, cutoff_time)

        regime_stats = []
        total_count = sum(row['count'] for row in rows)

        for row in rows:
            regime_stats.append({
                "regime": row['volatility_regime'],
                "count": row['count'],
                "percentage": (row['count'] / total_count * 100) if total_count > 0 else 0,
                "avg_volatility": float(row['avg_volatility']),
                "max_volatility": float(row['max_volatility']),
                "min_volatility": float(row['min_volatility'])
            })

        return {
            "period_days": days,
            "regime_statistics": regime_stats,
            "total_forecasts": total_count
        }

    finally:
        await conn.close()
