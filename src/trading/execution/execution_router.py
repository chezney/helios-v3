"""
src/trading/execution/execution_router.py

Execution Router - Dynamically routes orders to correct trading client based on current mode.

This is the central component for LIVE trading safety. It:
1. Queries database for current trading mode before EVERY trade
2. Routes to PaperTradingClient if mode is PAPER
3. Routes to VALRTradingClient if mode is LIVE
4. Provides hot-swapping capability (mode changes take effect immediately)
5. Logs all routing decisions for audit trail

Helios V3.0 - Phase 2: Execution Routing
Created: 2025-10-22
"""

import logging
from typing import Dict, Any, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession

from src.trading.execution.paper_trading_client import PaperTradingClient
from src.trading.execution.valr_trading_client import VALRTradingClient
from src.trading.execution.valr_websocket_trading_client import VALRWebSocketTradingClient
from src.trading.orchestrator.mode_orchestrator import TradingModeOrchestrator
from src.trading.orchestrator.live_safety_gates import LiveSafetyGates
import asyncio

logger = logging.getLogger(__name__)


class ExecutionRouter:
    """
    Execution Router - Routes orders to correct trading client based on current mode.

    Key Features:
    - Queries database for mode before EVERY trade (not cached)
    - Hot-swapping: Mode changes take effect immediately without restart
    - Dual client management: Maintains both PAPER and LIVE clients
    - Safety logging: All routing decisions logged for audit trail
    - Unified interface: Exposes same methods as trading clients

    Usage Example:
        router = ExecutionRouter(db_session)
        result = await router.place_market_order("BTCZAR", "BUY", 0.001)
        # Router automatically uses correct client based on current mode
    """

    def __init__(
        self,
        db_session: AsyncSession,
        initial_balance_zar: float = 100000.0,
        slippage_bps: float = 5.0
    ):
        """
        Initialize Execution Router.

        Args:
            db_session: Database session for mode queries
            initial_balance_zar: Starting balance for paper trading (default: 100,000 ZAR)
            slippage_bps: Base slippage for paper trading (default: 5 bps)
        """
        self.db = db_session

        # Initialize mode orchestrator for database queries
        self.mode_orchestrator = TradingModeOrchestrator(db_session)

        # Initialize LIVE Safety Gates (Phase 3)
        # ADJUSTED FOR TESTING WITH R960 CAPITAL (2025-10-23)
        # Once testing is successful, increase limits gradually
        self.safety_gates = LiveSafetyGates(
            db_session=db_session,
            max_order_size_zar=300.0,        # R300 max per trade (31% of R960 capital)
            max_daily_trades=50,             # 50 trades/day max (unchanged)
            min_order_value_zar=50.0,        # R50 minimum (VALR minimum ~R10)
            max_position_exposure_pct=30.0,  # 30% portfolio max per asset (unchanged)
            balance_buffer_pct=10.0          # 10% buffer for fees (increased from 5%)
        )

        # Initialize both trading clients
        # Paper Trading Client (always available)
        self.paper_client = PaperTradingClient(
            db_session=db_session,
            initial_balance_zar=initial_balance_zar,
            slippage_bps=slippage_bps
        )

        # LIVE Trading Client (WebSocket-enhanced, requires API credentials)
        try:
            # Use WebSocket-enhanced client for 2-3x faster execution
            self.live_client = VALRWebSocketTradingClient()
            # WebSocket connection will be established asynchronously
            self._websocket_connect_task = None
            logger.info("[OK] VALR WebSocket Trading Client initialized successfully")
            logger.info("[INFO] WebSocket connection will be established on first use")
        except ValueError as e:
            # API credentials not set - LIVE mode will be blocked
            self.live_client = None
            logger.warning(f"[WARN] VALR Trading Client not available: {e}")
            logger.warning("[WARN] LIVE trading will be disabled until credentials are configured")

        logger.info(
            f"ExecutionRouter initialized: "
            f"paper={self.paper_client is not None}, "
            f"live={self.live_client is not None}, "
            f"websocket_enabled={isinstance(self.live_client, VALRWebSocketTradingClient)}, "
            f"safety_gates=enabled"
        )

    async def _ensure_websocket_connected(self):
        """
        Ensure WebSocket connection is established for LIVE client.

        This is called before first LIVE trade to establish WebSocket connection.
        Connection is lazy-loaded to avoid blocking during initialization.
        """
        if isinstance(self.live_client, VALRWebSocketTradingClient):
            if not self.live_client.connected:
                logger.info("[ROUTER] Establishing WebSocket connection for LIVE trading...")
                connected = await self.live_client.connect()
                if connected:
                    logger.info("[OK] WebSocket connected successfully")
                else:
                    logger.warning("[WARN] WebSocket connection failed, will use REST fallback")

    async def _get_current_client(self) -> Union[PaperTradingClient, VALRTradingClient, VALRWebSocketTradingClient]:
        """
        Get the correct trading client based on CURRENT database mode.

        This method queries the database on EVERY call to ensure
        the mode is always up-to-date (no caching).

        For LIVE mode with WebSocket client, ensures WebSocket connection
        is established before returning client.

        Returns:
            PaperTradingClient if mode is PAPER
            VALRWebSocketTradingClient if mode is LIVE (WebSocket-enhanced)

        Raises:
            RuntimeError: If LIVE mode is active but VALR client not available
        """
        # Query database for current mode
        current_mode = await self.mode_orchestrator.get_current_mode()

        logger.debug(f"[ROUTER] Current trading mode: {current_mode}")

        if current_mode == "PAPER":
            logger.debug("[ROUTER] Routing to Paper Trading Client")
            return self.paper_client

        elif current_mode == "LIVE":
            if self.live_client is None:
                error_msg = (
                    "LIVE mode is active but VALR Trading Client is not available. "
                    "Please configure VALR_API_KEY and VALR_API_SECRET environment variables."
                )
                logger.error(f"[ROUTER ERROR] {error_msg}")
                raise RuntimeError(error_msg)

            # Ensure WebSocket connection for faster execution
            await self._ensure_websocket_connected()

            logger.warning("[ROUTER] 🔴 Routing to LIVE Trading Client (WebSocket) - REAL MONEY 🔴")
            return self.live_client

        else:
            raise ValueError(f"Invalid trading mode in database: {current_mode}")

    async def place_market_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place a market order through the appropriate trading client.

        This method (Phase 3 - with safety gates):
        1. Queries database for current mode
        2. Gets current market price
        3. **RUNS SAFETY CHECKS** (Phase 3 - only in LIVE mode)
        4. Routes to correct client (Paper or LIVE)
        5. Executes the order
        6. Logs routing decision

        Args:
            pair: Trading pair (e.g., "BTCZAR", "ETHZAR")
            side: "BUY" or "SELL"
            quantity: Quantity in base currency (BTC, ETH, etc.)
            metadata: Optional metadata for tracking

        Returns:
            Dict with order result from trading client

        Example:
            result = await router.place_market_order("BTCZAR", "BUY", 0.001)
            if result["success"]:
                print(f"Order filled at {result['fill_price']}")
        """
        # Log order details
        logger.info(
            f"[ROUTER] Market order request: {side} {quantity} {pair}"
        )

        # Get current mode and client
        current_mode = await self.mode_orchestrator.get_current_mode()
        client = await self._get_current_client()

        # Get current market price for safety checks
        # Use paper client to get price (works in both modes)
        try:
            from src.trading.execution.paper_trading_client import PaperTradingClient
            if isinstance(self.paper_client, PaperTradingClient):
                price = await self.paper_client._get_current_price(pair)
            else:
                # Fallback: estimate from recent candles
                price = 0.0  # Will be calculated by safety gates if needed
        except Exception as e:
            logger.warning(f"[ROUTER] Could not get current price: {e}, using 0")
            price = 0.0

        # **PHASE 3: RUN SAFETY CHECKS** (only in LIVE mode)
        safety_result = await self.safety_gates.validate_trade(
            pair=pair,
            side=side,
            quantity=quantity,
            price=price if price > 0 else 850000.0,  # Fallback price if unavailable
            current_mode=current_mode,
            trading_client=client
        )

        # If safety check failed, block the trade
        if not safety_result.passed:
            logger.error(
                f"[ROUTER] Trade BLOCKED by safety gates: {safety_result.reason}"
            )
            return {
                "success": False,
                "error": f"Safety check failed: {safety_result.reason}",
                "safety_check": safety_result.reason,
                "safety_details": safety_result.details,
                "blocked_by": "LiveSafetyGates",
                "pair": pair,
                "side": side,
                "quantity": quantity
            }

        # Safety checks passed - execute order
        logger.info(f"[ROUTER] Safety checks PASSED, executing order...")

        # Execute order through selected client
        result = await client.place_market_order(
            pair=pair,
            side=side,
            quantity=quantity,
            metadata=metadata
        )

        # Add router metadata to result
        result["routed_via"] = "ExecutionRouter"
        result["client_type"] = "PAPER" if client == self.paper_client else "LIVE"
        result["safety_checked"] = True
        result["safety_status"] = "passed"

        # Log result
        if result.get("success"):
            logger.info(
                f"[ROUTER] Market order executed successfully via {result['client_type']} client"
            )
        else:
            logger.error(
                f"[ROUTER] Market order failed: {result.get('error', 'Unknown error')}"
            )

        return result

    async def place_limit_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        post_only: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order through the appropriate trading client.

        Args:
            pair: Trading pair
            side: "BUY" or "SELL"
            quantity: Quantity in base currency
            price: Limit price in quote currency (ZAR)
            post_only: If True, order will only add liquidity (VALR only)
            metadata: Optional metadata

        Returns:
            Dict with order result
        """
        logger.info(
            f"[ROUTER] Limit order request: {side} {quantity} {pair} @ {price}"
        )

        # Get correct client
        client = await self._get_current_client()

        # Execute order
        # Note: PaperTradingClient doesn't support post_only parameter
        if client == self.paper_client:
            result = await client.place_limit_order(
                pair=pair,
                side=side,
                quantity=quantity,
                limit_price=price,
                metadata=metadata
            )
        else:
            result = await client.place_limit_order(
                pair=pair,
                side=side,
                quantity=quantity,
                price=price,
                post_only=post_only,
                metadata=metadata
            )

        # Add router metadata
        result["routed_via"] = "ExecutionRouter"
        result["client_type"] = "PAPER" if client == self.paper_client else "LIVE"

        return result

    async def get_balance(self, currency: str) -> float:
        """
        Get account balance for a specific currency.

        Routes to correct client based on current mode.

        Args:
            currency: Currency code (BTC, ETH, ZAR, etc.)

        Returns:
            Available balance
        """
        client = await self._get_current_client()
        balance = await client.get_balance(currency)

        logger.debug(
            f"[ROUTER] Balance query: {currency} = {balance:.8f} "
            f"(via {type(client).__name__})"
        )

        return balance

    async def get_all_balances(self) -> Dict[str, float]:
        """
        Get all account balances.

        Routes to correct client based on current mode.

        Returns:
            Dict of currency -> balance
        """
        client = await self._get_current_client()
        balances = await client.get_all_balances()

        logger.debug(
            f"[ROUTER] All balances query returned {len(balances)} currencies "
            f"(via {type(client).__name__})"
        )

        return balances

    async def get_current_mode(self) -> str:
        """
        Get current trading mode from database.

        This is a convenience method that directly queries the mode
        without routing through a client.

        Returns:
            "PAPER" or "LIVE"
        """
        mode = await self.mode_orchestrator.get_current_mode()
        logger.debug(f"[ROUTER] Current mode query: {mode}")
        return mode

    async def verify_routing(self) -> Dict[str, Any]:
        """
        Verify router configuration and current mode.

        This is a diagnostic method useful for testing and monitoring.

        Returns:
            Dict with router status:
            {
                "current_mode": "PAPER" or "LIVE",
                "paper_client_available": bool,
                "live_client_available": bool,
                "can_route_paper": bool,
                "can_route_live": bool,
                "warnings": List[str]
            }
        """
        current_mode = await self.mode_orchestrator.get_current_mode()

        warnings = []

        # Check if LIVE mode is active but client not available
        if current_mode == "LIVE" and self.live_client is None:
            warnings.append(
                "CRITICAL: LIVE mode is active but VALR client not configured. "
                "All trades will FAIL until VALR credentials are set."
            )

        status = {
            "current_mode": current_mode,
            "paper_client_available": self.paper_client is not None,
            "live_client_available": self.live_client is not None,
            "can_route_paper": self.paper_client is not None,
            "can_route_live": self.live_client is not None,
            "warnings": warnings
        }

        logger.info(f"[ROUTER] Verification: {status}")

        return status

    async def close(self):
        """
        Close HTTP sessions and cleanup resources.

        Call this during application shutdown.
        """
        if self.live_client:
            try:
                await self.live_client.close()
                logger.info("[ROUTER] VALR client session closed")
            except Exception as e:
                logger.error(f"[ROUTER] Error closing VALR client: {e}")

        # Paper client doesn't need cleanup

        logger.info("[ROUTER] ExecutionRouter closed")


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    from src.database import AsyncSessionLocal

    async def test_execution_router():
        """Test ExecutionRouter with both modes."""
        print("\n" + "=" * 80)
        print("EXECUTION ROUTER TEST")
        print("=" * 80 + "\n")

        async with AsyncSessionLocal() as db:
            # Initialize router
            router = ExecutionRouter(db_session=db)

            # Verify routing
            status = await router.verify_routing()
            print(f"Router Status: {status}")

            # Test mode query
            current_mode = await router.get_current_mode()
            print(f"\nCurrent Mode: {current_mode}")

            # Test balance query (safe operation)
            try:
                zar_balance = await router.get_balance("ZAR")
                print(f"ZAR Balance: R{zar_balance:,.2f}")
            except Exception as e:
                print(f"Balance query failed: {e}")

            # Cleanup
            await router.close()

        print("\n[OK] Test complete")

    asyncio.run(test_execution_router())
