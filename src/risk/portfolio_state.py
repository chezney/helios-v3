"""
Portfolio State Manager

Tracks portfolio value, peak value, and drawdown for risk management.
"""

import asyncpg
from typing import Dict
from datetime import datetime

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="portfolio_state")


class PortfolioStateManager:
    """
    Manage portfolio state (value, peak, drawdown).

    Tracks:
    - Total portfolio value in ZAR
    - Peak portfolio value (high watermark)
    - Current drawdown percentage
    - Maximum drawdown percentage
    """

    def __init__(self):
        pass

    async def get_portfolio_state(self) -> Dict[str, float]:
        """
        Get current portfolio state from database.

        Returns:
            Dict with total_value_zar, peak_value_zar, current_drawdown_pct, max_drawdown_pct
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            row = await conn.fetchrow("""
                SELECT total_value_zar, peak_value_zar,
                       current_drawdown_pct, max_drawdown_pct
                FROM portfolio_state
                WHERE id = 1
            """)

            if not row:
                # Portfolio state not initialized, use defaults
                logger.warning("Portfolio state not initialized, using defaults")
                return {
                    'total_value_zar': 100000.0,
                    'peak_value_zar': 100000.0,
                    'current_drawdown_pct': 0.0,
                    'max_drawdown_pct': 0.0
                }

            return {
                'total_value_zar': float(row['total_value_zar']),
                'peak_value_zar': float(row['peak_value_zar']),
                'current_drawdown_pct': float(row['current_drawdown_pct']),
                'max_drawdown_pct': float(row['max_drawdown_pct'])
            }

        finally:
            await conn.close()

    async def update_portfolio_state(self, new_total_value_zar: float) -> Dict[str, float]:
        """
        Update portfolio state with new total value.

        Recalculates peak value and drawdown.

        Args:
            new_total_value_zar: New total portfolio value in ZAR

        Returns:
            Updated portfolio state
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            # Get current state
            current_state = await self.get_portfolio_state()
            current_peak = current_state['peak_value_zar']
            current_max_dd = current_state['max_drawdown_pct']

            # Update peak if new value is higher
            new_peak = max(current_peak, new_total_value_zar)

            # Calculate current drawdown
            if new_peak > 0:
                current_drawdown_pct = ((new_peak - new_total_value_zar) / new_peak) * 100
            else:
                current_drawdown_pct = 0.0

            # Update max drawdown if current is larger
            new_max_dd = max(current_max_dd, current_drawdown_pct)

            # Update database
            await conn.execute("""
                UPDATE portfolio_state
                SET total_value_zar = $1,
                    peak_value_zar = $2,
                    current_drawdown_pct = $3,
                    max_drawdown_pct = $4,
                    last_updated = $5
                WHERE id = 1
            """,
                new_total_value_zar,
                new_peak,
                current_drawdown_pct,
                new_max_dd,
                datetime.utcnow()
            )

            logger.info(
                f"Portfolio state updated: Value={new_total_value_zar:,.0f} ZAR, "
                f"Peak={new_peak:,.0f} ZAR, Drawdown={current_drawdown_pct:.2f}%"
            )

            return {
                'total_value_zar': new_total_value_zar,
                'peak_value_zar': new_peak,
                'current_drawdown_pct': current_drawdown_pct,
                'max_drawdown_pct': new_max_dd
            }

        finally:
            await conn.close()

    async def calculate_total_value(self) -> float:
        """
        Calculate total portfolio value from positions and cash balance.

        This is a placeholder implementation. In production, this would:
        1. Query all open positions
        2. Get current market prices
        3. Calculate position values
        4. Add cash balance
        5. Return total

        For now, we just fetch from portfolio_state table.
        """
        state = await self.get_portfolio_state()
        return state['total_value_zar']

    async def initialize_portfolio_state(
        self,
        initial_value_zar: float = 100000.0
    ) -> None:
        """
        Initialize portfolio state with starting value.

        Only call this once when setting up the system.
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                INSERT INTO portfolio_state (
                    id, total_value_zar, peak_value_zar,
                    current_drawdown_pct, max_drawdown_pct, last_updated
                )
                VALUES (1, $1, $1, 0.0, 0.0, $2)
                ON CONFLICT (id) DO NOTHING
            """,
                initial_value_zar,
                datetime.utcnow()
            )

            logger.info(f"Portfolio state initialized with {initial_value_zar:,.0f} ZAR")

        finally:
            await conn.close()
