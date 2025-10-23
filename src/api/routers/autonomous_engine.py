"""
src/api/routers/autonomous_engine.py

API endpoints for autonomous trading engine control.

Helios V3.0 - Phase 6: Autonomous Trading Engine Control API
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, List
from pydantic import BaseModel
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from src.trading.autonomous.trading_engine import AutonomousTradingEngine, TradingMode, EngineStatus
from src.database import get_db_session

router = APIRouter(prefix="/api/autonomous-engine", tags=["Autonomous Engine"])
logger = logging.getLogger(__name__)

# Global engine instance (singleton)
_engine_instance: AutonomousTradingEngine = None
_engine_task: asyncio.Task = None
_db_session: AsyncSession = None


class EngineConfig(BaseModel):
    """Configuration for starting the autonomous engine"""
    trading_mode: str = "PAPER"  # "PAPER" or "LIVE"
    pairs: List[str] = ["BTCZAR", "ETHZAR", "SOLZAR"]
    auto_trading_enabled: bool = False


async def get_persistent_db_session() -> AsyncSession:
    """Get a persistent database session for the autonomous engine."""
    from src.database import AsyncSessionLocal
    return AsyncSessionLocal()


@router.post("/start")
async def start_engine(
    config: EngineConfig,
    background_tasks: BackgroundTasks
):
    """
    Start the autonomous trading engine.

    Args:
        config: Engine configuration (mode, pairs, auto-trading)

    Returns:
        Success response with configuration

    Raises:
        HTTPException 400: If engine is already running or invalid config
    """
    global _engine_instance, _engine_task, _db_session

    # Check if already running
    if _engine_instance and _engine_instance.status in [EngineStatus.RUNNING, EngineStatus.STARTING]:
        raise HTTPException(400, "Engine already running")

    try:
        # PROOF: Router start endpoint called
        with open("ROUTER_START_CALLED.txt", "w") as f:
            from datetime import datetime
            f.write(f"Router start endpoint called at {datetime.utcnow().isoformat()}\n")

        # Parse trading mode
        mode = TradingMode.PAPER if config.trading_mode.upper() == "PAPER" else TradingMode.LIVE

        # Require confirmation for LIVE mode
        if mode == TradingMode.LIVE:
            raise HTTPException(
                400,
                "LIVE mode requires explicit confirmation via Mode Orchestrator first"
            )

        # PROOF: About to create DB session
        with open("ROUTER_BEFORE_DB.txt", "w") as f:
            f.write(f"About to create DB session\n")

        # Create persistent database session
        _db_session = await get_persistent_db_session()

        # PROOF: About to create engine instance
        with open("ROUTER_BEFORE_ENGINE.txt", "w") as f:
            f.write(f"About to create engine instance\n")

        # Create engine instance
        _engine_instance = AutonomousTradingEngine(
            db_session=_db_session,
            trading_mode=mode,
            pairs=config.pairs
        )

        # PROOF: Engine instance created
        with open("ROUTER_ENGINE_CREATED.txt", "w") as f:
            f.write(f"Engine instance created: {_engine_instance}\n")
            f.write(f"Status: {_engine_instance.status}\n")

        # Enable auto-trading if requested
        if config.auto_trading_enabled:
            _engine_instance.enable_auto_trading()

        # PROOF: About to create background task
        with open("ROUTER_BEFORE_TASK.txt", "w") as f:
            f.write(f"About to create background task\n")

        # Start engine in background
        async def run_engine():
            with open("ROUTER_RUN_ENGINE_CALLED.txt", "w") as f:
                f.write(f"run_engine() called\n")
            try:
                with open("ROUTER_BEFORE_START.txt", "w") as f:
                    f.write(f"About to call engine.start()\n")
                await _engine_instance.start()
                with open("ROUTER_AFTER_START.txt", "w") as f:
                    f.write(f"engine.start() returned\n")
            except Exception as e:
                logger.error(f"Engine error: {e}", exc_info=True)
                with open("ROUTER_ENGINE_ERROR.txt", "w") as f:
                    f.write(f"Error: {e}\n")
                if _engine_instance:
                    _engine_instance.status = EngineStatus.ERROR

        _engine_task = asyncio.create_task(run_engine())

        # PROOF: Task created
        with open("ROUTER_TASK_CREATED.txt", "w") as f:
            f.write(f"Task created: {_engine_task}\n")

        logger.info(f"Autonomous engine started: mode={mode.value}, pairs={config.pairs}")

        return {
            "success": True,
            "message": "Autonomous trading engine started",
            "config": {
                "trading_mode": mode.value,
                "pairs": config.pairs,
                "auto_trading_enabled": config.auto_trading_enabled
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start engine: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to start engine: {str(e)}")


@router.post("/stop")
async def stop_engine():
    """
    Stop the autonomous trading engine.

    Returns:
        Success response

    Raises:
        HTTPException 400: If engine is not running
    """
    global _engine_instance, _engine_task, _db_session

    if not _engine_instance:
        raise HTTPException(400, "Engine not running")

    try:
        # Shutdown engine gracefully
        await _engine_instance.shutdown()

        # Cancel background task
        if _engine_task and not _engine_task.done():
            _engine_task.cancel()
            try:
                await _engine_task
            except asyncio.CancelledError:
                pass

        # Close database session
        if _db_session:
            await _db_session.close()
            _db_session = None

        # Clear instance
        _engine_instance = None
        _engine_task = None

        logger.info("Autonomous engine stopped")

        return {
            "success": True,
            "message": "Autonomous trading engine stopped"
        }

    except Exception as e:
        logger.error(f"Failed to stop engine: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to stop engine: {str(e)}")


@router.get("/status")
async def get_engine_status(db: AsyncSession = Depends(get_db_session)):
    """
    Get current engine status.

    Returns:
        Engine status including mode, flags, and health metrics

    If engine is not running, returns stopped status.
    """
    if not _engine_instance:
        return {
            "status": "STOPPED",
            "message": "Engine not running"
        }

    # Get status from engine
    status = _engine_instance.get_status()

    # CRITICAL FIX: Query database for CURRENT trading mode
    # The engine may have been started in PAPER mode, but user could have switched to LIVE
    from src.trading.orchestrator.mode_orchestrator import TradingModeOrchestrator
    orchestrator = TradingModeOrchestrator(db)
    current_mode = await orchestrator.get_current_mode()

    # Override the trading_mode with current database value
    status["trading_mode"] = current_mode

    return status


@router.post("/auto-trading/enable")
async def enable_auto_trading():
    """
    Enable autonomous trading.

    Returns:
        Success response

    Raises:
        HTTPException 400: If engine is not running
    """
    if not _engine_instance:
        raise HTTPException(400, "Engine not running")

    _engine_instance.enable_auto_trading()

    logger.info("Auto-trading enabled")

    return {
        "success": True,
        "message": "Auto-trading enabled"
    }


@router.post("/auto-trading/disable")
async def disable_auto_trading():
    """
    Disable autonomous trading.

    Returns:
        Success response

    Raises:
        HTTPException 400: If engine is not running
    """
    if not _engine_instance:
        raise HTTPException(400, "Engine not running")

    _engine_instance.disable_auto_trading()

    logger.info("Auto-trading disabled")

    return {
        "success": True,
        "message": "Auto-trading disabled"
    }


@router.post("/emergency-stop")
async def trigger_emergency_stop():
    """
    Trigger emergency stop (close all positions and halt trading).

    Returns:
        Success response

    Raises:
        HTTPException 400: If engine is not running
    """
    if not _engine_instance:
        raise HTTPException(400, "Engine not running")

    await _engine_instance._trigger_emergency_stop()

    logger.critical("Emergency stop triggered via API")

    return {
        "success": True,
        "message": "Emergency stop triggered, all positions closed"
    }


@router.post("/emergency-stop/clear")
async def clear_emergency_stop():
    """
    Clear emergency stop flag.

    Returns:
        Success response

    Raises:
        HTTPException 400: If engine is not running
    """
    if not _engine_instance:
        raise HTTPException(400, "Engine not running")

    _engine_instance.clear_emergency_stop()

    logger.info("Emergency stop cleared via API")

    return {
        "success": True,
        "message": "Emergency stop cleared"
    }


@router.get("/metrics")
async def get_engine_metrics(db: AsyncSession = Depends(get_db_session)):
    """
    Get engine performance metrics.

    Returns:
        Portfolio metrics, position counts, and system performance
    """
    from sqlalchemy import text

    try:
        # Get portfolio state
        portfolio_query = text("""
            SELECT total_value_zar, current_drawdown_pct,
                   (total_value_zar - peak_value_zar) as total_pnl_zar,
                   0.0 as daily_pnl_zar
            FROM portfolio_state
            WHERE id = 1
        """)
        portfolio_result = await db.execute(portfolio_query)
        portfolio_row = portfolio_result.fetchone()

        # Get position counts
        position_query = text("""
            SELECT
                status,
                COUNT(*) as count,
                COALESCE(SUM(pnl_zar), 0) as total_pnl
            FROM positions
            GROUP BY status
        """)
        position_result = await db.execute(position_query)
        position_rows = position_result.fetchall()

        # Build response
        metrics = {
            "portfolio": {
                "total_value_zar": float(portfolio_row[0]) if portfolio_row else 0.0,
                "current_drawdown_pct": float(portfolio_row[1]) if portfolio_row else 0.0,
                "total_pnl_zar": float(portfolio_row[2]) if portfolio_row else 0.0,
                "daily_pnl_zar": float(portfolio_row[3]) if portfolio_row else 0.0
            },
            "positions": {}
        }

        for row in position_rows:
            status = row[0]
            count = row[1]
            total_pnl = float(row[2])

            metrics["positions"][status] = {
                "count": count,
                "total_pnl_zar": total_pnl
            }

        # Add engine status if running
        if _engine_instance:
            metrics["engine"] = _engine_instance.get_status()

        return metrics

    except Exception as e:
        logger.error(f"Error fetching metrics: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to fetch metrics: {str(e)}")


@router.get("/trade-decisions")
async def get_trade_decisions(
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get trade decisions with reasons (approved and rejected).

    Returns:
        List of trade decisions showing:
        - ML predictions
        - Risk calculations
        - LLM approvals/rejections
        - Portfolio risk rejections
        - Execution status

    Args:
        limit: Number of recent decisions to return (default 50)
    """
    from sqlalchemy import text

    try:
        # Query aether_risk_decisions table for all decisions
        query = text("""
            SELECT
                ard.id,
                ard.pair,
                ard.signal,
                ard.ml_confidence,
                ard.position_size_zar,
                ard.leverage,
                ard.stop_loss_pct,
                ard.take_profit_pct,
                ard.executed,
                ard.execution_id,
                ard.rejected_by,
                ard.rejection_reason,
                ard.llm_rejection_reasoning,
                ard.created_at
            FROM aether_risk_decisions ard
            ORDER BY ard.created_at DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"limit": limit})
        rows = result.fetchall()

        decisions = []
        for row in rows:
            # Determine status and reason
            executed = row[8]
            rejected_by = row[10]
            rejection_reason = row[11]
            llm_reasoning = row[12]

            if executed:
                # Trade was executed successfully
                status = "EXECUTED"
                reason = "Executed successfully"
            elif rejected_by:
                # Trade was rejected by a tier
                status = "REJECTED"
                reason = rejection_reason if rejection_reason else f"Rejected by {rejected_by}"
                # Add LLM reasoning if available
                if llm_reasoning:
                    reason = f"{reason}: {llm_reasoning}"
            else:
                # Trade was approved by Aether but NOT executed and NOT rejected
                # This means execution FAILED without recording rejection
                status = "FAILED"
                reason = "Execution failed - no rejection reason recorded (check logs)"

            decision = {
                "id": row[0],
                "pair": row[1],
                "signal": row[2],
                "ml_confidence": float(row[3]) if row[3] else 0.0,
                "position_size_zar": float(row[4]) if row[4] else 0.0,
                "leverage": float(row[5]) if row[5] else 1.0,
                "stop_loss_pct": float(row[6]) if row[6] else 0.0,
                "take_profit_pct": float(row[7]) if row[7] else 0.0,
                "executed": executed,
                "execution_id": row[9],
                "rejected_by": rejected_by,
                "rejection_reason": rejection_reason,
                "llm_rejection_reasoning": llm_reasoning,
                "created_at": row[13].isoformat() if row[13] else None,
                "status": status,
                "reason": reason
            }
            decisions.append(decision)

        return {
            "total": len(decisions),
            "decisions": decisions
        }

    except Exception as e:
        logger.error(f"Error fetching trade decisions: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to fetch trade decisions: {str(e)}")
