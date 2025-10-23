"""
Tier 4 API Router - LLM Strategic Execution Layer

Endpoints:
- GET /api/tier4/health - Health check
- POST /api/tier4/evaluate-trade/{pair} - Evaluate trade with LLM
- GET /api/tier4/context/{pair} - Get market context
- GET /api/tier4/decisions/recent - Get recent strategic decisions
- PUT /api/tier4/provider - Switch LLM provider
"""

import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.database import get_db_session
from src.llm.strategy.strategic_execution import StrategicExecutionLayer
from src.llm.context.market_context import MarketContextAggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier4", tags=["tier4"])

# Global LLM provider (can be switched at runtime)
CURRENT_LLM_PROVIDER = "anthropic"


# ============================================================
# Pydantic Models
# ============================================================

class TradeEvaluationRequest(BaseModel):
    """Request model for trade evaluation."""
    signal: str = Field(..., description="BUY or SELL")
    confidence: float = Field(..., ge=0.0, le=1.0, description="ML confidence (0.0-1.0)")
    position_size_zar: float = Field(..., gt=0, description="Position size in ZAR")
    leverage: float = Field(default=1.0, ge=1.0, le=5.0, description="Leverage multiplier")
    stop_loss_pct: float = Field(..., gt=0, description="Stop loss percentage")
    take_profit_pct: float = Field(..., gt=0, description="Take profit percentage")
    max_loss_zar: float = Field(..., description="Maximum loss in ZAR")
    expected_gain_zar: float = Field(..., description="Expected gain in ZAR")


class ProviderSwitchRequest(BaseModel):
    """Request model for switching LLM provider."""
    provider: str = Field(..., description="anthropic or openrouter")


# ============================================================
# Endpoints
# ============================================================

@router.get("/health")
async def tier4_health(db: AsyncSession = Depends(get_db_session)):
    """
    Health check for Tier 4 (LLM Strategic Layer).

    Checks:
    - Database connectivity
    - LLM strategic decisions table exists
    - Current LLM provider configuration
    """
    try:
        # Check database connectivity
        result = await db.execute(text("SELECT 1"))
        result.fetchone()

        # Check if tables exist
        tables_query = await db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('llm_strategic_decisions', 'market_context_snapshots')
        """))
        tables = [row[0] for row in tables_query.fetchall()]

        # Get recent decisions count
        count_query = await db.execute(text("""
            SELECT COUNT(*) FROM llm_strategic_decisions
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """))
        recent_decisions = count_query.scalar()

        return {
            "status": "healthy",
            "tier": "Tier 4 - LLM Strategic Execution",
            "llm_provider": CURRENT_LLM_PROVIDER,
            "database": "connected",
            "tables": {
                "llm_strategic_decisions": "llm_strategic_decisions" in tables,
                "market_context_snapshots": "market_context_snapshots" in tables
            },
            "recent_decisions_24h": recent_decisions
        }

    except Exception as e:
        logger.error(f"Tier 4 health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Tier 4 unhealthy: {str(e)}")


@router.post("/evaluate-trade/{pair}")
async def evaluate_trade(
    pair: str,
    request: TradeEvaluationRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Evaluate proposed trade using LLM strategic analysis.

    Args:
        pair: Trading pair (e.g., BTCZAR)
        request: Trade parameters from Tier 3

    Returns:
        Strategic decision with reasoning and modifications
    """
    try:
        # Initialize strategic execution layer
        strategic_layer = StrategicExecutionLayer(db, llm_provider=CURRENT_LLM_PROVIDER)

        # Convert request to dict
        trade_params = {
            'position_size_zar': request.position_size_zar,
            'leverage': request.leverage,
            'stop_loss_pct': request.stop_loss_pct,
            'take_profit_pct': request.take_profit_pct,
            'max_loss_zar': request.max_loss_zar,
            'expected_gain_zar': request.expected_gain_zar
        }

        # Evaluate trade
        result = await strategic_layer.evaluate_trade(
            pair=pair,
            signal=request.signal,
            confidence=request.confidence,
            trade_params=trade_params
        )

        return {
            "pair": pair,
            "approved": result['approved'],
            "decision": result['decision'],
            "final_trade_params": result['final_trade_params'],
            "strategic_reasoning": result['strategic_reasoning'],
            "risk_flags": result['risk_flags'],
            "llm_provider": CURRENT_LLM_PROVIDER,
            "modifications": result.get('modifications_applied')
        }

    except Exception as e:
        logger.error(f"Trade evaluation failed for {pair}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Trade evaluation failed: {str(e)}")


@router.get("/context/{pair}")
async def get_market_context(
    pair: str,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get current market context for a trading pair.

    Useful for debugging and analysis.

    Args:
        pair: Trading pair (e.g., BTCZAR)

    Returns:
        Complete market context dict
    """
    try:
        aggregator = MarketContextAggregator(db)
        context = await aggregator.build_context(pair)

        return {
            "pair": pair,
            "context": context
        }

    except Exception as e:
        logger.error(f"Failed to get market context for {pair}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get context: {str(e)}")


@router.get("/decisions/recent")
async def get_recent_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    approved_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get recent strategic decisions.

    Args:
        limit: Number of decisions to return (1-100)
        approved_only: Only return approved decisions

    Returns:
        List of recent strategic decisions
    """
    try:
        # Build query
        query_str = """
            SELECT
                id, pair, signal, ml_confidence,
                proposed_position_size_zar, proposed_leverage,
                llm_decision, llm_reasoning,
                confidence_adjustment, position_size_multiplier,
                risk_flags, final_approved,
                final_position_size_zar,
                llm_provider, llm_model,
                created_at
            FROM llm_strategic_decisions
        """

        if approved_only:
            query_str += " WHERE final_approved = TRUE"

        query_str += " ORDER BY created_at DESC LIMIT :limit"

        result = await db.execute(text(query_str), {'limit': limit})
        rows = result.fetchall()

        decisions = []
        for row in rows:
            decisions.append({
                'id': row[0],
                'pair': row[1],
                'signal': row[2],
                'ml_confidence': float(row[3]) if row[3] else None,
                'proposed_position_size_zar': float(row[4]) if row[4] else None,
                'proposed_leverage': float(row[5]) if row[5] else None,
                'llm_decision': row[6],
                'llm_reasoning': row[7],
                'confidence_adjustment': float(row[8]) if row[8] else None,
                'position_size_multiplier': float(row[9]) if row[9] else None,
                'risk_flags': row[10].split(',') if row[10] else [],
                'final_approved': row[11],
                'final_position_size_zar': float(row[12]) if row[12] else None,
                'llm_provider': row[13],
                'llm_model': row[14],
                'created_at': row[15].isoformat() if row[15] else None
            })

        return {
            "count": len(decisions),
            "decisions": decisions
        }

    except Exception as e:
        logger.error(f"Failed to get recent decisions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get decisions: {str(e)}")


@router.put("/provider")
async def switch_llm_provider(request: ProviderSwitchRequest):
    """
    Switch LLM provider (Claude <-> GPT-4).

    Args:
        request: Provider name (anthropic or openrouter)

    Returns:
        Confirmation of provider switch
    """
    global CURRENT_LLM_PROVIDER

    if request.provider not in ['anthropic', 'openrouter']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {request.provider}. Must be 'anthropic' or 'openrouter'"
        )

    old_provider = CURRENT_LLM_PROVIDER
    CURRENT_LLM_PROVIDER = request.provider

    logger.info(f"Switched LLM provider: {old_provider} -> {CURRENT_LLM_PROVIDER}")

    return {
        "status": "success",
        "previous_provider": old_provider,
        "current_provider": CURRENT_LLM_PROVIDER,
        "message": f"LLM provider switched to {CURRENT_LLM_PROVIDER}"
    }


@router.get("/stats")
async def get_tier4_stats(db: AsyncSession = Depends(get_db_session)):
    """
    Get Tier 4 statistics.

    Returns:
        Statistics about strategic decisions
    """
    try:
        # Get decision counts by type
        decision_stats = await db.execute(text("""
            SELECT
                llm_decision,
                COUNT(*) as count,
                AVG(confidence_adjustment) as avg_conf_adj,
                AVG(position_size_multiplier) as avg_size_mult
            FROM llm_strategic_decisions
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY llm_decision
        """))

        stats = {}
        for row in decision_stats.fetchall():
            stats[row[0]] = {
                'count': row[1],
                'avg_confidence_adjustment': float(row[2]) if row[2] else 0.0,
                'avg_position_size_multiplier': float(row[3]) if row[3] else 1.0
            }

        # Get approval rate
        approval_query = await db.execute(text("""
            SELECT
                COUNT(CASE WHEN final_approved = TRUE THEN 1 END) as approved,
                COUNT(*) as total
            FROM llm_strategic_decisions
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """))
        approval_row = approval_query.fetchone()
        approved = approval_row[0] if approval_row else 0
        total = approval_row[1] if approval_row else 0
        approval_rate = (approved / total * 100) if total > 0 else 0

        return {
            "period": "last_7_days",
            "total_evaluations": total,
            "approval_rate": round(approval_rate, 2),
            "decision_breakdown": stats,
            "current_provider": CURRENT_LLM_PROVIDER
        }

    except Exception as e:
        logger.error(f"Failed to get Tier 4 stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
