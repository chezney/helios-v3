"""
src/trading/orchestrator/mode_orchestrator.py

Mode Orchestrator - manages PAPER vs LIVE trading mode switching.

Helios V3.0 - Phase 6: Trading Mode Management
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TradingModeOrchestrator:
    """
    Manages trading mode switching between PAPER and LIVE modes.

    Features:
    - Mode persistence to database
    - Safe mode transitions
    - Confirmation requirements for LIVE mode
    - Mode status tracking
    - Historical mode change logging
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the Mode Orchestrator.

        Args:
            db_session: Database session
        """
        self.db = db_session
        self.current_mode: Optional[str] = None
        self._load_current_mode_sync = False

    async def get_current_mode(self) -> str:
        """
        Get the current trading mode from database.

        Returns:
            Current mode: "PAPER" or "LIVE"
        """
        query = text("""
            SELECT current_mode
            FROM trading_mode_state
            WHERE id = 1
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        if not row:
            # Initialize with PAPER mode if not exists
            await self._initialize_mode_state()
            return "PAPER"

        mode = row[0]
        self.current_mode = mode
        return mode

    async def set_mode(
        self,
        new_mode: str,
        confirmed: bool = False,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Set the trading mode.

        Args:
            new_mode: "PAPER" or "LIVE"
            confirmed: Confirmation flag (required for LIVE mode)
            reason: Reason for mode change (optional)

        Returns:
            Dict with success status and details

        Raises:
            ValueError: If mode is invalid or confirmation missing
        """
        # Validate mode
        if new_mode not in ["PAPER", "LIVE"]:
            raise ValueError(f"Invalid mode: {new_mode}. Must be PAPER or LIVE")

        # Get current mode
        current_mode = await self.get_current_mode()

        # Check if already in requested mode
        if current_mode == new_mode:
            logger.info(f"Already in {new_mode} mode, no change needed")
            return {
                "success": True,
                "message": f"Already in {new_mode} mode",
                "previous_mode": current_mode,
                "new_mode": new_mode,
                "changed": False
            }

        # Require confirmation for switching to LIVE mode
        if new_mode == "LIVE" and not confirmed:
            raise ValueError(
                "Switching to LIVE mode requires explicit confirmation. "
                "Set confirmed=True to proceed with real trading."
            )

        # Log mode change
        logger.warning(
            f"⚠️ TRADING MODE CHANGE: {current_mode} → {new_mode} "
            f"(Reason: {reason or 'Not specified'})"
        )

        # Update database
        update_query = text("""
            UPDATE trading_mode_state
            SET
                current_mode = :new_mode,
                last_changed_at = :timestamp,
                changed_by = :changed_by,
                change_reason = :reason
            WHERE id = 1
        """)

        await self.db.execute(
            update_query,
            {
                "new_mode": new_mode,
                "timestamp": datetime.utcnow(),
                "changed_by": "orchestrator",
                "reason": reason or "Manual mode change"
            }
        )
        await self.db.commit()

        # Log to history
        await self._log_mode_change(current_mode, new_mode, reason)

        # Update cached mode
        self.current_mode = new_mode

        return {
            "success": True,
            "message": f"Trading mode changed: {current_mode} → {new_mode}",
            "previous_mode": current_mode,
            "new_mode": new_mode,
            "changed": True,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason
        }

    async def enable_live_mode(self, confirmed: bool = False, reason: str = None) -> Dict[str, Any]:
        """
        Enable LIVE trading mode.

        Args:
            confirmed: Explicit confirmation required
            reason: Reason for enabling LIVE mode

        Returns:
            Mode change result
        """
        return await self.set_mode("LIVE", confirmed=confirmed, reason=reason)

    async def enable_paper_mode(self, reason: str = None) -> Dict[str, Any]:
        """
        Enable PAPER trading mode (no confirmation required).

        Args:
            reason: Reason for switching to PAPER mode

        Returns:
            Mode change result
        """
        return await self.set_mode("PAPER", confirmed=True, reason=reason)

    async def get_mode_status(self) -> Dict[str, Any]:
        """
        Get comprehensive mode status including history.

        Returns:
            Dict with current mode, last change time, and recent history
        """
        # Get current mode state
        query = text("""
            SELECT
                current_mode,
                last_changed_at,
                changed_by,
                change_reason
            FROM trading_mode_state
            WHERE id = 1
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        if not row:
            await self._initialize_mode_state()
            return {
                "current_mode": "PAPER",
                "last_changed_at": None,
                "changed_by": None,
                "change_reason": "Initial state"
            }

        # Get recent history
        history_query = text("""
            SELECT
                from_mode,
                to_mode,
                changed_at,
                reason
            FROM trading_mode_history
            ORDER BY changed_at DESC
            LIMIT 10
        """)

        history_result = await self.db.execute(history_query)
        history_rows = history_result.fetchall()

        history = []
        for h_row in history_rows:
            history.append({
                "from_mode": h_row[0],
                "to_mode": h_row[1],
                "changed_at": h_row[2].isoformat() if h_row[2] else None,
                "reason": h_row[3]
            })

        return {
            "current_mode": row[0],
            "last_changed_at": row[1].isoformat() if row[1] else None,
            "changed_by": row[2],
            "change_reason": row[3],
            "recent_history": history
        }

    async def _initialize_mode_state(self):
        """Initialize trading mode state table with PAPER mode."""
        insert_query = text("""
            INSERT INTO trading_mode_state (id, current_mode, last_changed_at, changed_by, change_reason)
            VALUES (1, 'PAPER', :timestamp, 'system', 'Initial state')
            ON CONFLICT (id) DO NOTHING
        """)

        await self.db.execute(insert_query, {"timestamp": datetime.utcnow()})
        await self.db.commit()

        logger.info("Initialized trading mode state: PAPER")

    async def _log_mode_change(self, from_mode: str, to_mode: str, reason: Optional[str]):
        """
        Log mode change to history table.

        Args:
            from_mode: Previous mode
            to_mode: New mode
            reason: Reason for change
        """
        insert_query = text("""
            INSERT INTO trading_mode_history (from_mode, to_mode, changed_at, reason)
            VALUES (:from_mode, :to_mode, :timestamp, :reason)
        """)

        await self.db.execute(
            insert_query,
            {
                "from_mode": from_mode,
                "to_mode": to_mode,
                "timestamp": datetime.utcnow(),
                "reason": reason or "Not specified"
            }
        )
        await self.db.commit()

        logger.info(f"Logged mode change: {from_mode} → {to_mode}")

    async def is_live_mode(self) -> bool:
        """
        Check if currently in LIVE trading mode.

        Returns:
            True if LIVE mode, False if PAPER mode
        """
        mode = await self.get_current_mode()
        return mode == "LIVE"

    async def is_paper_mode(self) -> bool:
        """
        Check if currently in PAPER trading mode.

        Returns:
            True if PAPER mode, False if LIVE mode
        """
        mode = await self.get_current_mode()
        return mode == "PAPER"
