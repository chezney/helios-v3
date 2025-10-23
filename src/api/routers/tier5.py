"""
src/api/routers/tier5.py

Tier 5 (Portfolio Manager) API endpoints.

Helios V3.0 - Phase 5: Guardian Portfolio Manager
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import logging

from src.database import get_db_session
from src.portfolio.risk.portfolio_risk_manager import PortfolioRiskManager, PortfolioRiskLimits
from src.portfolio.optimization.mpt_optimizer import MPTOptimizer
from src.portfolio.positions.position_manager import PositionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier5", tags=["Tier 5 - Portfolio Manager"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TradeCheckRequest(BaseModel):
    """Request to check if trade passes risk limits."""
    pair: str = Field(..., description="Trading pair (e.g., BTCZAR)")
    signal: str = Field(..., description="BUY or SELL")
    position_size_zar: float = Field(..., gt=0, description="Position size in ZAR")
    leverage: float = Field(..., ge=1.0, le=5.0, description="Leverage (1.0 - 5.0)")
    stop_loss_pct: float = Field(..., gt=0, description="Stop loss percentage")
    take_profit_pct: float = Field(..., gt=0, description="Take profit percentage")


class OptimizationRequest(BaseModel):
    """Request to calculate optimal portfolio weights."""
    pairs: List[str] = Field(..., description="List of trading pairs")
    ml_predictions: Dict[str, float] = Field(..., description="Expected returns by pair")
    confidence_scores: Dict[str, float] = Field(..., description="Confidence scores (0-1) by pair")


class OpenPositionRequest(BaseModel):
    """Request to open a new position."""
    pair: str
    signal: str
    position_size_zar: float
    leverage: float
    stop_loss_pct: float
    take_profit_pct: float
    max_loss_zar: float
    expected_gain_zar: float
    strategic_reasoning: str = ""


# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db_session)):
    """
    Health check for Tier 5 Portfolio Manager.

    Verifies:
    - Database connection
    - Portfolio state table exists
    - Positions table exists
    """
    try:
        # Check portfolio_state table
        result = await db.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN ('portfolio_state', 'positions', 'portfolio_snapshots', 'rebalancing_events')
        """))
        table_count = result.scalar()

        # Get portfolio state
        portfolio_result = await db.execute(text("SELECT total_value_zar, current_drawdown_pct FROM portfolio_state WHERE id = 1"))
        portfolio_row = portfolio_result.fetchone()

        if portfolio_row:
            total_value = float(portfolio_row[0])
            drawdown = float(portfolio_row[1])
        else:
            total_value = 0.0
            drawdown = 0.0

        # Count open positions
        pos_result = await db.execute(text("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'"))
        open_positions = pos_result.scalar()

        return {
            "status": "healthy" if table_count == 4 else "degraded",
            "tier": "Tier 5 - Portfolio Manager",
            "tables_found": table_count,
            "tables_expected": 4,
            "portfolio_value_zar": total_value,
            "current_drawdown_pct": drawdown,
            "open_positions": open_positions,
            "components": {
                "risk_manager": "operational",
                "mpt_optimizer": "operational",
                "position_manager": "operational"
            }
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# ============================================================================
# RISK MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/risk/check-trade")
async def check_trade_risk(
    request: TradeCheckRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Check if proposed trade passes all portfolio risk limits.

    Runs 7 risk checks:
    1. Portfolio drawdown limit
    2. Daily loss limit
    3. Max open positions
    4. Single position size
    5. Sector exposure
    6. Correlation exposure
    7. Portfolio leverage
    """
    try:
        risk_manager = PortfolioRiskManager(db)

        trade_params = {
            'position_size_zar': request.position_size_zar,
            'leverage': request.leverage,
            'stop_loss_pct': request.stop_loss_pct,
            'take_profit_pct': request.take_profit_pct
        }

        result = await risk_manager.check_trade_risk(
            pair=request.pair,
            signal=request.signal,
            trade_params=trade_params
        )

        return {
            "pair": request.pair,
            "signal": request.signal,
            "passed": result.passed,
            "reason": result.reason,
            "current_metrics": result.current_metrics,
            "violated_limits": result.violated_limits
        }

    except Exception as e:
        logger.error(f"Risk check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Risk check failed: {str(e)}")


@router.get("/risk/limits")
async def get_risk_limits():
    """Get current portfolio risk limits."""
    limits = PortfolioRiskLimits()
    return {
        "max_drawdown_pct": limits.max_drawdown_pct,
        "max_single_position_pct": limits.max_single_position_pct,
        "max_sector_exposure_pct": limits.max_sector_exposure_pct,
        "max_correlation_threshold": limits.max_correlation_threshold,
        "daily_loss_limit_pct": limits.daily_loss_limit_pct,
        "max_open_positions": limits.max_open_positions,
        "max_leverage": limits.max_leverage
    }


# ============================================================================
# PORTFOLIO OPTIMIZATION ENDPOINTS
# ============================================================================

@router.post("/optimization/optimal-weights")
async def calculate_optimal_weights(
    request: OptimizationRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Calculate optimal portfolio weights using Black-Litterman model.

    Uses Modern Portfolio Theory to combine:
    - Market equilibrium (prior)
    - ML predictions (views)
    - Covariance matrix (risk model)

    Returns weights that maximize Sharpe ratio.
    """
    try:
        optimizer = MPTOptimizer(db)

        optimal_weights = await optimizer.calculate_optimal_weights(
            pairs=request.pairs,
            ml_predictions=request.ml_predictions,
            confidence_scores=request.confidence_scores
        )

        # Calculate portfolio metrics
        metrics = await optimizer.calculate_portfolio_metrics(
            weights=optimal_weights,
            expected_returns=request.ml_predictions
        )

        return {
            "optimal_weights": optimal_weights,
            "expected_return_annual": metrics['expected_return_annual'],
            "volatility_annual": metrics['volatility_annual'],
            "sharpe_ratio": metrics['sharpe_ratio'],
            "model": "Black-Litterman"
        }

    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.get("/optimization/portfolio-metrics")
async def get_portfolio_metrics(db: AsyncSession = Depends(get_db_session)):
    """Get current portfolio metrics (return, volatility, Sharpe ratio)."""
    try:
        # Get current portfolio weights from open positions
        query = text("""
            SELECT
                pair,
                SUM(position_value_zar) as total_value
            FROM positions
            WHERE status = 'OPEN'
            GROUP BY pair
        """)

        result = await db.execute(query)
        rows = result.fetchall()

        if not rows:
            return {
                "message": "No open positions",
                "weights": {},
                "metrics": None
            }

        # Calculate weights
        total_value = sum(float(r[1]) for r in rows)
        weights = {r[0]: float(r[1]) / total_value for r in rows}

        # Get expected returns (from recent ML predictions)
        expected_returns = {}
        for pair in weights.keys():
            pred_query = text("""
                SELECT prediction, confidence_score
                FROM ml_predictions
                WHERE pair = :pair
                ORDER BY created_at DESC
                LIMIT 1
            """)
            pred_result = await db.execute(pred_query, {'pair': pair})
            pred_row = pred_result.fetchone()

            if pred_row:
                # Simple expected return estimate
                expected_returns[pair] = 0.05 if pred_row[0] == 'BUY' else -0.05
            else:
                expected_returns[pair] = 0.0

        # Calculate metrics
        optimizer = MPTOptimizer(db)
        metrics = await optimizer.calculate_portfolio_metrics(
            weights=weights,
            expected_returns=expected_returns
        )

        return {
            "current_weights": weights,
            "expected_return_annual": metrics['expected_return_annual'],
            "volatility_annual": metrics['volatility_annual'],
            "sharpe_ratio": metrics['sharpe_ratio']
        }

    except Exception as e:
        logger.error(f"Portfolio metrics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Portfolio metrics failed: {str(e)}")


# ============================================================================
# POSITION MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/positions/open")
async def open_position(
    request: OpenPositionRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Open a new position.

    Steps:
    1. Execute market order (via VALR or paper trading)
    2. Record position in database
    3. Set stop loss and take profit levels
    """
    try:
        position_manager = PositionManager(db, trading_client=None)  # Paper trading mode

        trade_params = {
            'position_size_zar': request.position_size_zar,
            'leverage': request.leverage,
            'stop_loss_pct': request.stop_loss_pct,
            'take_profit_pct': request.take_profit_pct,
            'max_loss_zar': request.max_loss_zar,
            'expected_gain_zar': request.expected_gain_zar
        }

        result = await position_manager.open_position(
            pair=request.pair,
            signal=request.signal,
            trade_params=trade_params,
            strategic_reasoning=request.strategic_reasoning
        )

        return result

    except Exception as e:
        logger.error(f"Open position failed: {e}")
        raise HTTPException(status_code=500, detail=f"Open position failed: {str(e)}")


@router.get("/positions")
async def list_positions(
    status: Optional[str] = None,
    pair: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session)
):
    """
    List positions.

    Query parameters:
    - status: Filter by status (OPEN, CLOSED, STOPPED_OUT, TAKE_PROFIT, TIMEOUT)
    - pair: Filter by trading pair
    - limit: Max number of results (default 50)
    """
    try:
        # Build query
        where_clauses = []
        params = {}

        if status:
            where_clauses.append("status = :status")
            params['status'] = status

        if pair:
            where_clauses.append("pair = :pair")
            params['pair'] = pair

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = text(f"""
            SELECT
                id, pair, signal, entry_price, quantity, position_value_zar,
                leverage, stop_loss_price, take_profit_price, entry_time,
                exit_price, exit_time, pnl_pct, pnl_zar, status, close_reason
            FROM positions
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        params['limit'] = limit
        result = await db.execute(query, params)
        rows = result.fetchall()

        positions = []
        for row in rows:
            positions.append({
                "id": row[0],
                "pair": row[1],
                "signal": row[2],
                "entry_price": float(row[3]) if row[3] else None,
                "quantity": float(row[4]) if row[4] else None,
                "position_value_zar": float(row[5]) if row[5] else None,
                "leverage": float(row[6]) if row[6] else None,
                "stop_loss_price": float(row[7]) if row[7] else None,
                "take_profit_price": float(row[8]) if row[8] else None,
                "entry_time": row[9].isoformat() if row[9] else None,
                "exit_price": float(row[10]) if row[10] else None,
                "exit_time": row[11].isoformat() if row[11] else None,
                "pnl_pct": float(row[12]) if row[12] else None,
                "pnl_zar": float(row[13]) if row[13] else None,
                "status": row[14],
                "close_reason": row[15]
            })

        return {
            "positions": positions,
            "count": len(positions),
            "filters": {
                "status": status,
                "pair": pair,
                "limit": limit
            }
        }

    except Exception as e:
        logger.error(f"List positions failed: {e}")
        raise HTTPException(status_code=500, detail=f"List positions failed: {str(e)}")


@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: int,
    reason: str = "MANUAL",
    db: AsyncSession = Depends(get_db_session)
):
    """
    Close a position.

    Args:
        position_id: Position ID to close
        reason: Reason for closing (MANUAL, STOP_LOSS, TAKE_PROFIT, TIMEOUT)
    """
    try:
        position_manager = PositionManager(db, trading_client=None)  # Paper trading mode

        result = await position_manager.close_position(
            position_id=position_id,
            reason=reason
        )

        return result

    except Exception as e:
        logger.error(f"Close position failed: {e}")
        raise HTTPException(status_code=500, detail=f"Close position failed: {str(e)}")


@router.get("/positions/monitor")
async def monitor_positions(db: AsyncSession = Depends(get_db_session)):
    """
    Monitor all open positions for SL/TP triggers.

    Returns list of positions that need action.
    """
    try:
        position_manager = PositionManager(db)

        actions = await position_manager.monitor_positions()

        return {
            "actions_needed": len(actions),
            "actions": actions
        }

    except Exception as e:
        logger.error(f"Monitor positions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Monitor positions failed: {str(e)}")


# ============================================================================
# PORTFOLIO SUMMARY ENDPOINTS
# ============================================================================

@router.get("/portfolio/summary")
async def get_portfolio_summary(db: AsyncSession = Depends(get_db_session)):
    """
    Get comprehensive portfolio summary.

    Includes:
    - Total value, P&L, drawdown
    - Open positions count and breakdown
    - Risk utilization
    """
    try:
        # Get portfolio state
        portfolio_query = text("""
            SELECT total_value_zar, peak_value_zar, current_drawdown_pct,
                   max_drawdown_pct, last_updated
            FROM portfolio_state
            WHERE id = 1
        """)
        portfolio_result = await db.execute(portfolio_query)
        portfolio_row = portfolio_result.fetchone()

        if not portfolio_row:
            raise HTTPException(status_code=404, detail="Portfolio state not found")

        # Get open positions
        positions_query = text("""
            SELECT pair, COUNT(*) as count, SUM(position_value_zar) as total_value
            FROM positions
            WHERE status = 'OPEN'
            GROUP BY pair
        """)
        positions_result = await db.execute(positions_query)
        positions_rows = positions_result.fetchall()

        positions_by_pair = {row[0]: {"count": row[1], "value": float(row[2])} for row in positions_rows}

        # Calculate daily P&L
        daily_pnl_query = text("""
            SELECT SUM(pnl_zar) as daily_pnl
            FROM positions
            WHERE exit_time >= CURRENT_DATE
        """)
        daily_pnl_result = await db.execute(daily_pnl_query)
        daily_pnl_row = daily_pnl_result.fetchone()
        daily_pnl = float(daily_pnl_row[0]) if daily_pnl_row and daily_pnl_row[0] else 0.0

        return {
            "total_value_zar": float(portfolio_row[0]),
            "peak_value_zar": float(portfolio_row[1]),
            "current_drawdown_pct": float(portfolio_row[2]),
            "max_drawdown_pct": float(portfolio_row[3]),
            "daily_pnl_zar": daily_pnl,
            "daily_pnl_pct": daily_pnl / float(portfolio_row[0]) if float(portfolio_row[0]) > 0 else 0.0,
            "last_updated": portfolio_row[4].isoformat() if portfolio_row[4] else None,
            "open_positions": positions_by_pair,
            "total_open_positions": sum(p["count"] for p in positions_by_pair.values())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Portfolio summary failed: {str(e)}")


@router.get("/rejection-details/{decision_id}")
async def get_rejection_details(
    decision_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get detailed rejection information for a trade decision.

    Returns:
        - rejected_by: Which tier rejected the trade
        - rejection_reason: Brief reason for rejection
        - llm_decision_data: Full context sent to LLM (if applicable)
        - llm_rejection_reasoning: LLM's detailed explanation (if applicable)
        - Full trade parameters that were rejected
    """
    try:
        query = text("""
            SELECT
                id, pair, signal, ml_confidence,
                kelly_fraction, fractional_kelly, volatility_adjusted_fraction,
                position_size_zar, leverage,
                stop_loss_pct, take_profit_pct,
                daily_volatility, volatility_regime,
                portfolio_value_zar, drawdown_pct,
                executed, rejected_by, rejection_reason,
                llm_decision_data, llm_rejection_reasoning,
                created_at
            FROM aether_risk_decisions
            WHERE id = :decision_id
        """)

        result = await db.execute(query, {'decision_id': decision_id})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

        import json

        response = {
            "id": row[0],
            "pair": row[1],
            "signal": row[2],
            "ml_confidence": float(row[3]),
            "kelly_analysis": {
                "kelly_fraction": float(row[4]) if row[4] else None,
                "fractional_kelly": float(row[5]) if row[5] else None,
                "volatility_adjusted_fraction": float(row[6]) if row[6] else None
            },
            "trade_parameters": {
                "position_size_zar": float(row[7]),
                "leverage": float(row[8]),
                "stop_loss_pct": float(row[9]),
                "take_profit_pct": float(row[10])
            },
            "market_conditions": {
                "daily_volatility": float(row[11]),
                "volatility_regime": row[12]
            },
            "portfolio_state": {
                "portfolio_value_zar": float(row[13]),
                "drawdown_pct": float(row[14])
            },
            "execution_status": {
                "executed": row[15],
                "rejected_by": row[16],
                "rejection_reason": row[17]
            },
            "llm_analysis": {
                "decision_data": json.loads(row[18]) if row[18] else None,
                "rejection_reasoning": row[19]
            },
            "timestamp": row[20].isoformat() if row[20] else None
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch rejection details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch rejection details: {str(e)}")


@router.get("/recent-decisions")
async def get_recent_decisions(
    limit: int = 10,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get recent risk decisions (both executed and rejected).

    This endpoint returns a summary of recent aether_risk_decisions,
    showing both trades that were executed and those that were rejected.
    """
    try:
        query = text("""
            SELECT
                id,
                pair,
                signal,
                ml_confidence,
                executed,
                rejected_by,
                rejection_reason,
                created_at
            FROM aether_risk_decisions
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"limit": limit})
        rows = result.fetchall()

        decisions = []
        for row in rows:
            decisions.append({
                "id": row[0],
                "pair": row[1],
                "signal": row[2],
                "ml_confidence": float(row[3]),
                "executed": row[4],
                "rejected_by": row[5],
                "rejection_reason": row[6],
                "created_at": row[7].isoformat() if row[7] else None
            })

        return {"decisions": decisions}

    except Exception as e:
        logger.error(f"Failed to fetch recent decisions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent decisions: {str(e)}")


logger.info("Tier 5 (Portfolio Manager) router initialized")
