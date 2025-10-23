"""
Mode Management API Router
Handles trading mode switching (PAPER ↔ LIVE)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.trading.orchestrator.mode_orchestrator import TradingModeOrchestrator
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mode", tags=["mode"])


class SetModeRequest(BaseModel):
    mode: str
    confirmed: bool = False
    reason: str = "API mode change"


@router.get("/current")
async def get_current_mode(db: AsyncSession = Depends(get_db)):
    """Get current trading mode"""
    try:
        orchestrator = TradingModeOrchestrator(db)
        mode = await orchestrator.get_current_mode()

        from datetime import datetime, timezone
        return {
            "mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting current mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set")
async def set_mode(request: SetModeRequest, db: AsyncSession = Depends(get_db)):
    """
    Set trading mode (PAPER or LIVE)

    Requires confirmation for LIVE mode switch.
    """
    try:
        orchestrator = TradingModeOrchestrator(db)

        # Validate mode
        if request.mode not in ["PAPER", "LIVE"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {request.mode}. Must be PAPER or LIVE"
            )

        # Require confirmation for LIVE mode
        if request.mode == "LIVE" and not request.confirmed:
            raise HTTPException(
                status_code=400,
                detail="LIVE mode requires confirmation (confirmed=true)"
            )

        # Set the mode
        await orchestrator.set_mode(
            new_mode=request.mode,
            confirmed=request.confirmed,
            reason=request.reason
        )

        # Get updated mode to confirm
        new_mode = await orchestrator.get_current_mode()

        logger.info(f"Trading mode changed to {new_mode} via API")

        return {
            "success": True,
            "mode": new_mode,
            "message": f"Trading mode set to {new_mode}",
            "reason": request.reason
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_mode_history(db: AsyncSession = Depends(get_db), limit: int = 10):
    """Get recent mode changes"""
    try:
        orchestrator = TradingModeOrchestrator(db)
        history = await orchestrator.get_mode_history(limit=limit)

        return {
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting mode history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
