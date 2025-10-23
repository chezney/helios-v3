"""
src/trading/orchestrator/live_safety_gates.py

LIVE Trading Safety Gates - Pre-execution validation for LIVE mode trades

This module provides critical safety checks to prevent dangerous trading in LIVE mode.
All checks are ONLY applied when trading mode is LIVE (bypassed in PAPER mode).

Safety Gates:
1. Balance Validation: Ensure sufficient funds before trade
2. Order Size Limits: Enforce maximum order size per trade
3. Daily Trade Limits: Prevent runaway trading (max trades per day)
4. Position Exposure Limits: Prevent excessive portfolio concentration
5. Minimum Order Value: Prevent dust trades that waste fees

Helios V3.0 - Phase 3: LIVE Safety Gates
Created: 2025-10-22
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    passed: bool
    reason: str
    details: Optional[Dict[str, Any]] = None


class LiveSafetyGates:
    """
    LIVE Trading Safety Gates - Pre-execution validation.

    This class implements safety checks that ONLY apply in LIVE mode.
    All checks are bypassed when trading in PAPER mode.

    Safety Philosophy:
    - Fail-safe: Block trade if any check fails
    - Conservative: Use safe defaults
    - Transparent: Log all check results
    - Configurable: Allow user to adjust limits

    Usage:
        gates = LiveSafetyGates(db_session)
        result = await gates.validate_trade(
            pair="BTCZAR",
            side="BUY",
            quantity=0.001,
            price=850000.0,
            current_mode="LIVE"
        )
        if not result.passed:
            # Block trade
            logger.error(f"Trade blocked: {result.reason}")
    """

    # Default safety limits (conservative values)
    DEFAULT_MAX_ORDER_SIZE_ZAR = 10000.0  # R10,000 max per trade
    DEFAULT_MAX_DAILY_TRADES = 50  # 50 trades per day max
    DEFAULT_MIN_ORDER_VALUE_ZAR = 100.0  # R100 minimum (VALR minimum ~R10)
    DEFAULT_MAX_POSITION_EXPOSURE_PCT = 30.0  # 30% of portfolio max per asset
    DEFAULT_BALANCE_BUFFER_PCT = 5.0  # Keep 5% buffer for fees

    def __init__(
        self,
        db_session: AsyncSession,
        max_order_size_zar: float = None,
        max_daily_trades: int = None,
        min_order_value_zar: float = None,
        max_position_exposure_pct: float = None,
        balance_buffer_pct: float = None
    ):
        """
        Initialize LIVE Safety Gates.

        Args:
            db_session: Database session for queries
            max_order_size_zar: Maximum order size in ZAR (default: R10,000)
            max_daily_trades: Maximum trades per day (default: 50)
            min_order_value_zar: Minimum order value in ZAR (default: R100)
            max_position_exposure_pct: Max portfolio exposure per asset (default: 30%)
            balance_buffer_pct: Balance buffer for fees (default: 5%)
        """
        self.db = db_session

        # Use provided limits or defaults
        self.max_order_size_zar = max_order_size_zar or self.DEFAULT_MAX_ORDER_SIZE_ZAR
        self.max_daily_trades = max_daily_trades or self.DEFAULT_MAX_DAILY_TRADES
        self.min_order_value_zar = min_order_value_zar or self.DEFAULT_MIN_ORDER_VALUE_ZAR
        self.max_position_exposure_pct = max_position_exposure_pct or self.DEFAULT_MAX_POSITION_EXPOSURE_PCT
        self.balance_buffer_pct = balance_buffer_pct or self.DEFAULT_BALANCE_BUFFER_PCT

        logger.info(
            f"LiveSafetyGates initialized: "
            f"max_order=R{self.max_order_size_zar:,.0f}, "
            f"max_daily_trades={self.max_daily_trades}, "
            f"min_order=R{self.min_order_value_zar:,.0f}"
        )

    async def validate_trade(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        current_mode: str,
        trading_client: Any = None
    ) -> SafetyCheckResult:
        """
        Run all safety checks on a proposed trade.

        This is the main entry point for safety validation.
        Runs ALL safety checks in sequence and blocks trade if ANY fail.

        Args:
            pair: Trading pair (e.g., "BTCZAR")
            side: "BUY" or "SELL"
            quantity: Quantity in base currency
            price: Current price in quote currency
            current_mode: Current trading mode ("PAPER" or "LIVE")
            trading_client: Optional trading client for balance queries

        Returns:
            SafetyCheckResult with passed=True if all checks pass,
            or passed=False with reason if any check fails
        """
        # CRITICAL: Bypass all checks if in PAPER mode
        if current_mode != "LIVE":
            logger.debug(f"[SAFETY] Bypassing safety checks (mode={current_mode})")
            return SafetyCheckResult(
                passed=True,
                reason="PAPER mode - safety checks bypassed"
            )

        logger.info(f"[SAFETY] Running LIVE safety checks for {side} {quantity} {pair}")

        # Calculate order value
        order_value_zar = quantity * price

        # Check 1: Minimum order value
        result = await self._check_minimum_order_value(order_value_zar)
        if not result.passed:
            return result

        # Check 2: Maximum order size
        result = await self._check_maximum_order_size(order_value_zar)
        if not result.passed:
            return result

        # Check 3: Daily trade limit
        result = await self._check_daily_trade_limit()
        if not result.passed:
            return result

        # Check 4: Balance validation (if trading client provided)
        if trading_client:
            result = await self._check_sufficient_balance(
                pair=pair,
                side=side,
                quantity=quantity,
                price=price,
                trading_client=trading_client
            )
            if not result.passed:
                return result

        # Check 5: Position exposure limit
        result = await self._check_position_exposure(pair, side, order_value_zar)
        if not result.passed:
            return result

        # All checks passed
        logger.info(f"[SAFETY] All safety checks PASSED for {side} {quantity} {pair}")
        return SafetyCheckResult(
            passed=True,
            reason="All safety checks passed"
        )

    async def _check_minimum_order_value(self, order_value_zar: float) -> SafetyCheckResult:
        """
        Check if order value meets minimum threshold.

        Prevents dust trades that waste fees.

        Args:
            order_value_zar: Order value in ZAR

        Returns:
            SafetyCheckResult
        """
        if order_value_zar < self.min_order_value_zar:
            return SafetyCheckResult(
                passed=False,
                reason=f"Order value R{order_value_zar:,.2f} below minimum R{self.min_order_value_zar:,.2f}",
                details={
                    "order_value": order_value_zar,
                    "minimum": self.min_order_value_zar
                }
            )

        logger.debug(f"[SAFETY] Minimum order value check PASSED: R{order_value_zar:,.2f}")
        return SafetyCheckResult(passed=True, reason="Minimum order value met")

    async def _check_maximum_order_size(self, order_value_zar: float) -> SafetyCheckResult:
        """
        Check if order size is within safe limits.

        Prevents accidentally placing huge orders.

        Args:
            order_value_zar: Order value in ZAR

        Returns:
            SafetyCheckResult
        """
        if order_value_zar > self.max_order_size_zar:
            return SafetyCheckResult(
                passed=False,
                reason=f"Order value R{order_value_zar:,.2f} exceeds maximum R{self.max_order_size_zar:,.2f}",
                details={
                    "order_value": order_value_zar,
                    "maximum": self.max_order_size_zar
                }
            )

        logger.debug(f"[SAFETY] Maximum order size check PASSED: R{order_value_zar:,.2f}")
        return SafetyCheckResult(passed=True, reason="Order size within limits")

    async def _check_daily_trade_limit(self) -> SafetyCheckResult:
        """
        Check if daily trade limit has been exceeded.

        Prevents runaway trading from bugs or misconfiguration.

        Returns:
            SafetyCheckResult
        """
        try:
            # Count LIVE trades today (from paper_trading_orders or positions table)
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Check positions table for today's trades
            query = text("""
                SELECT COUNT(*)
                FROM positions
                WHERE opened_at >= :today_start
            """)

            result = await self.db.execute(query, {"today_start": today_start})
            trades_today = result.scalar() or 0

            if trades_today >= self.max_daily_trades:
                return SafetyCheckResult(
                    passed=False,
                    reason=f"Daily trade limit exceeded: {trades_today}/{self.max_daily_trades} trades today",
                    details={
                        "trades_today": trades_today,
                        "limit": self.max_daily_trades
                    }
                )

            logger.debug(f"[SAFETY] Daily trade limit check PASSED: {trades_today}/{self.max_daily_trades}")
            return SafetyCheckResult(passed=True, reason="Daily trade limit not exceeded")

        except Exception as e:
            logger.error(f"[SAFETY] Error checking daily trade limit: {e}")
            # Fail-safe: Block trade if check fails
            return SafetyCheckResult(
                passed=False,
                reason=f"Daily trade limit check failed: {e}"
            )

    async def _check_sufficient_balance(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        trading_client: Any
    ) -> SafetyCheckResult:
        """
        Check if account has sufficient balance for the trade.

        Args:
            pair: Trading pair
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Order price
            trading_client: Trading client to query balance

        Returns:
            SafetyCheckResult
        """
        try:
            # Calculate required amount with buffer for fees
            order_value_zar = quantity * price
            fee_estimate = order_value_zar * 0.001  # 0.1% taker fee
            buffer = order_value_zar * (self.balance_buffer_pct / 100.0)
            total_required = order_value_zar + fee_estimate + buffer

            if side == "BUY":
                # Check ZAR balance
                zar_balance = await trading_client.get_balance("ZAR")

                if zar_balance < total_required:
                    return SafetyCheckResult(
                        passed=False,
                        reason=f"Insufficient ZAR balance: R{zar_balance:,.2f} < R{total_required:,.2f} required",
                        details={
                            "available": zar_balance,
                            "required": total_required,
                            "order_value": order_value_zar,
                            "fee_estimate": fee_estimate,
                            "buffer": buffer
                        }
                    )

                logger.debug(f"[SAFETY] Balance check PASSED: R{zar_balance:,.2f} available")

            else:  # SELL
                # Check base currency balance (BTC, ETH, etc.)
                base_currency = pair.replace("ZAR", "")
                base_balance = await trading_client.get_balance(base_currency)

                if base_balance < quantity:
                    return SafetyCheckResult(
                        passed=False,
                        reason=f"Insufficient {base_currency} balance: {base_balance:.8f} < {quantity:.8f} required",
                        details={
                            "currency": base_currency,
                            "available": base_balance,
                            "required": quantity
                        }
                    )

                logger.debug(f"[SAFETY] Balance check PASSED: {base_balance:.8f} {base_currency} available")

            return SafetyCheckResult(passed=True, reason="Sufficient balance available")

        except Exception as e:
            logger.error(f"[SAFETY] Error checking balance: {e}")
            # Fail-safe: Block trade if balance check fails
            return SafetyCheckResult(
                passed=False,
                reason=f"Balance check failed: {e}"
            )

    async def _check_position_exposure(
        self,
        pair: str,
        side: str,
        order_value_zar: float
    ) -> SafetyCheckResult:
        """
        Check if trade would create excessive position exposure.

        Prevents over-concentration in single asset.

        Args:
            pair: Trading pair
            side: "BUY" or "SELL"
            order_value_zar: Order value in ZAR

        Returns:
            SafetyCheckResult
        """
        try:
            # Only check for BUY orders (SELL reduces exposure)
            if side != "BUY":
                return SafetyCheckResult(passed=True, reason="SELL order reduces exposure")

            # Get current portfolio value
            portfolio_query = text("""
                SELECT total_value_zar
                FROM portfolio_state
                WHERE id = 1
            """)
            result = await self.db.execute(portfolio_query)
            row = result.fetchone()

            if not row:
                # No portfolio state yet - allow trade
                return SafetyCheckResult(passed=True, reason="No portfolio state to check")

            portfolio_value = float(row[0])

            # Get current exposure to this pair
            exposure_query = text("""
                SELECT COALESCE(SUM(position_size_zar), 0)
                FROM positions
                WHERE pair = :pair AND status = 'OPEN'
            """)
            result = await self.db.execute(exposure_query, {"pair": pair})
            current_exposure = float(result.scalar() or 0)

            # Calculate new exposure after this trade
            new_exposure = current_exposure + order_value_zar

            # Check if new exposure exceeds limit
            exposure_pct = (new_exposure / portfolio_value) * 100.0
            if exposure_pct > self.max_position_exposure_pct:
                return SafetyCheckResult(
                    passed=False,
                    reason=f"Position exposure too high: {exposure_pct:.1f}% > {self.max_position_exposure_pct:.1f}% limit",
                    details={
                        "pair": pair,
                        "current_exposure_zar": current_exposure,
                        "new_exposure_zar": new_exposure,
                        "portfolio_value_zar": portfolio_value,
                        "exposure_pct": exposure_pct,
                        "limit_pct": self.max_position_exposure_pct
                    }
                )

            logger.debug(f"[SAFETY] Position exposure check PASSED: {exposure_pct:.1f}%")
            return SafetyCheckResult(passed=True, reason="Position exposure within limits")

        except Exception as e:
            logger.error(f"[SAFETY] Error checking position exposure: {e}")
            # Fail-safe: Block trade if check fails
            return SafetyCheckResult(
                passed=False,
                reason=f"Position exposure check failed: {e}"
            )

    def update_limits(
        self,
        max_order_size_zar: Optional[float] = None,
        max_daily_trades: Optional[int] = None,
        min_order_value_zar: Optional[float] = None,
        max_position_exposure_pct: Optional[float] = None
    ):
        """
        Update safety limits (allows runtime configuration).

        Args:
            max_order_size_zar: New maximum order size
            max_daily_trades: New daily trade limit
            min_order_value_zar: New minimum order value
            max_position_exposure_pct: New position exposure limit
        """
        if max_order_size_zar is not None:
            self.max_order_size_zar = max_order_size_zar
            logger.info(f"[SAFETY] Updated max_order_size_zar: R{max_order_size_zar:,.2f}")

        if max_daily_trades is not None:
            self.max_daily_trades = max_daily_trades
            logger.info(f"[SAFETY] Updated max_daily_trades: {max_daily_trades}")

        if min_order_value_zar is not None:
            self.min_order_value_zar = min_order_value_zar
            logger.info(f"[SAFETY] Updated min_order_value_zar: R{min_order_value_zar:,.2f}")

        if max_position_exposure_pct is not None:
            self.max_position_exposure_pct = max_position_exposure_pct
            logger.info(f"[SAFETY] Updated max_position_exposure_pct: {max_position_exposure_pct:.1f}%")

    def get_current_limits(self) -> Dict[str, Any]:
        """
        Get current safety limits.

        Returns:
            Dict with all current limits
        """
        return {
            "max_order_size_zar": self.max_order_size_zar,
            "max_daily_trades": self.max_daily_trades,
            "min_order_value_zar": self.min_order_value_zar,
            "max_position_exposure_pct": self.max_position_exposure_pct,
            "balance_buffer_pct": self.balance_buffer_pct
        }
