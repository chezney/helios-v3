"""
src/trading/autonomous/error_recovery.py

Error recovery mechanisms for Autonomous Trading Engine.

Components:
1. WebSocketRecoveryManager - WebSocket reconnection with exponential backoff
2. DatabaseRecoveryManager - Database connection recovery
3. RateLimitHandler - API rate limiting for VALR and LLM APIs
4. TierRecoveryManager - Tier component reinitialization on failure

Helios V3.0 - Phase 6: Week 27 Error Recovery System
"""

import asyncio
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


class WebSocketRecoveryManager:
    """
    Manages WebSocket reconnection with exponential backoff.

    Features:
    - Exponential backoff (1s, 2s, 4s, 8s, ..., max 60s)
    - Maximum retry attempts configurable
    - Success/failure callbacks
    - Tracks last disconnect time and retry count
    """

    def __init__(self, max_retries: int = 10):
        """
        Initialize WebSocket recovery manager.

        Args:
            max_retries: Maximum number of reconnection attempts (default: 10)
        """
        self.max_retries = max_retries
        self.retry_count = 0
        self.last_disconnect: Optional[datetime] = None
        self.backoff_seconds = 1

        logger.info(f"WebSocket recovery manager initialized (max retries: {max_retries})")

    async def reconnect_with_backoff(
        self,
        connect_func: Callable,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None
    ) -> bool:
        """
        Reconnect to WebSocket with exponential backoff.

        Backoff schedule:
        - Attempt 1: 1 second
        - Attempt 2: 2 seconds
        - Attempt 3: 4 seconds
        - Attempt 4: 8 seconds
        - ...
        - Max: 60 seconds

        Args:
            connect_func: Async function to call for reconnection
            on_success: Optional callback on successful reconnect
            on_failure: Optional callback if all retries fail

        Returns:
            True if reconnected successfully, False otherwise
        """
        self.last_disconnect = datetime.utcnow()

        logger.warning(
            f"WebSocket disconnected at {self.last_disconnect.strftime('%Y-%m-%d %H:%M:%S UTC')}. "
            f"Starting reconnection attempts..."
        )

        for attempt in range(1, self.max_retries + 1):
            self.retry_count = attempt

            # Calculate backoff time (exponential: 2^(attempt-1), max 60s)
            wait_time = min(2 ** (attempt - 1), 60)

            logger.warning(
                f"WebSocket reconnection attempt {attempt}/{self.max_retries} "
                f"(waiting {wait_time}s)..."
            )

            await asyncio.sleep(wait_time)

            try:
                # Attempt reconnection
                await connect_func()

                # Success!
                logger.info(f"[OK] WebSocket reconnected successfully on attempt {attempt}")
                self.retry_count = 0
                self.backoff_seconds = 1

                if on_success:
                    await on_success()

                return True

            except Exception as e:
                logger.error(f"[FAIL] Reconnection attempt {attempt} failed: {e}")

                if attempt == self.max_retries:
                    logger.critical(
                        f"[CRITICAL] WebSocket reconnection failed after {self.max_retries} attempts. "
                        f"Total downtime: {(datetime.utcnow() - self.last_disconnect).total_seconds():.0f}s"
                    )

                    if on_failure:
                        await on_failure()

                    return False

        return False

    def reset(self):
        """Reset reconnection state."""
        self.retry_count = 0
        self.backoff_seconds = 1
        self.last_disconnect = None
        logger.info("WebSocket recovery state reset")

    def get_stats(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        return {
            "retry_count": self.retry_count,
            "last_disconnect": self.last_disconnect.isoformat() if self.last_disconnect else None,
            "max_retries": self.max_retries
        }


class DatabaseRecoveryManager:
    """
    Manages database connection recovery.

    Features:
    - Automatic retry on database errors
    - Session recreation
    - Configurable retry delays
    - Error logging and tracking
    """

    def __init__(self, db_session_factory, retry_delay: int = 5, max_retries: int = 5):
        """
        Initialize database recovery manager.

        Args:
            db_session_factory: Factory function to create new database sessions
            retry_delay: Seconds to wait between retries (default: 5)
            max_retries: Maximum retry attempts (default: 5)
        """
        self.db_session_factory = db_session_factory
        self.retry_delay = retry_delay
        self.max_retries = max_retries

        logger.info(
            f"Database recovery manager initialized "
            f"(retry delay: {retry_delay}s, max retries: {max_retries})"
        )

    async def execute_with_retry(
        self,
        query_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute database query with automatic retry on failure.

        Args:
            query_func: Async function that performs database operation
            *args, **kwargs: Arguments to pass to query_func

        Returns:
            Result from query_func

        Raises:
            Exception: If all retries fail
        """
        from sqlalchemy.exc import OperationalError, DBAPIError

        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await query_func(*args, **kwargs)

                if attempt > 1:
                    logger.info(f"[OK] Database operation succeeded on attempt {attempt}")

                return result

            except (OperationalError, DBAPIError) as e:
                last_error = e

                logger.warning(
                    f"[WARN] Database operation failed (attempt {attempt}/{self.max_retries}): {e}"
                )

                if attempt == self.max_retries:
                    logger.critical(
                        f"[CRITICAL] Database operation failed after {self.max_retries} attempts"
                    )
                    raise

                # Wait before retry
                logger.info(f"Waiting {self.retry_delay}s before retry...")
                await asyncio.sleep(self.retry_delay)

                # Try to recreate database session
                try:
                    logger.info("Attempting to recreate database session...")
                    # Note: Session recreation depends on your session management
                    # This is a placeholder - implement based on your architecture
                except Exception as session_error:
                    logger.error(f"Failed to recreate session: {session_error}")

            except Exception as e:
                logger.error(f"Unexpected database error: {e}", exc_info=True)
                raise

        if last_error:
            raise last_error


class RateLimitHandler:
    """
    Handles API rate limiting for VALR and LLM APIs.

    Features:
    - Token bucket algorithm
    - Configurable requests per minute
    - Automatic waiting when limit reached
    - Per-minute sliding window
    """

    def __init__(self, max_requests_per_minute: int = 60):
        """
        Initialize rate limit handler.

        Args:
            max_requests_per_minute: Maximum API requests allowed per minute (default: 60)
        """
        self.max_requests = max_requests_per_minute
        self.request_timestamps = deque()

        logger.info(f"Rate limit handler initialized ({max_requests_per_minute} req/min)")

    async def wait_if_rate_limited(self):
        """
        Wait if rate limit would be exceeded.

        Uses sliding window approach:
        - Tracks request timestamps
        - Removes timestamps older than 1 minute
        - Waits if at limit
        """
        now = datetime.utcnow()

        # Remove timestamps older than 1 minute
        cutoff = now - timedelta(minutes=1)

        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()

        # Check if at limit
        if len(self.request_timestamps) >= self.max_requests:
            # Calculate wait time
            oldest = self.request_timestamps[0]
            wait_until = oldest + timedelta(minutes=1)
            wait_seconds = (wait_until - now).total_seconds()

            if wait_seconds > 0:
                logger.warning(
                    f"[WARN] Rate limit reached ({self.max_requests}/min). "
                    f"Waiting {wait_seconds:.1f}s..."
                )
                await asyncio.sleep(wait_seconds)

                # Clean up old timestamps after waiting
                now = datetime.utcnow()
                cutoff = now - timedelta(minutes=1)
                while self.request_timestamps and self.request_timestamps[0] < cutoff:
                    self.request_timestamps.popleft()

        # Record this request
        self.request_timestamps.append(datetime.utcnow())

    def reset(self):
        """Reset rate limit counter."""
        self.request_timestamps.clear()
        logger.info("Rate limit counter reset")

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limit statistics."""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        # Count recent requests
        recent_requests = sum(1 for ts in self.request_timestamps if ts >= cutoff)

        return {
            "requests_last_minute": recent_requests,
            "max_requests_per_minute": self.max_requests,
            "utilization_pct": (recent_requests / self.max_requests) * 100
        }


class TierRecoveryManager:
    """
    Manages tier component recovery and reinitialization.

    Features:
    - Track health of all tier components
    - Reinitialize failed components
    - Prevents cascading failures
    - Health status reporting
    """

    def __init__(self, engine):
        """
        Initialize tier recovery manager.

        Args:
            engine: Reference to AutonomousTradingEngine instance
        """
        self.engine = engine
        self.tier_health = {
            "predictor": True,
            "aether_engine": True,
            "strategic_layer": True,
            "portfolio_risk_manager": True,
            "position_manager": True,
            "candle_generator": True
        }

        self.failure_counts = {tier: 0 for tier in self.tier_health.keys()}
        self.max_failures_before_alert = 3

        logger.info("Tier recovery manager initialized")

    async def reinitialize_tier(self, tier_name: str) -> bool:
        """
        Reinitialize a failed tier component.

        Args:
            tier_name: Name of tier to reinitialize
                - "predictor" (Tier 2: Neural Network)
                - "aether_engine" (Tier 3: Risk Management)
                - "strategic_layer" (Tier 4: LLM Strategy)
                - "portfolio_risk_manager" (Tier 5: Portfolio Risk)
                - "position_manager" (Tier 5: Position Management)
                - "candle_generator" (Tier 1: Data Streaming)

        Returns:
            True if successful, False otherwise
        """
        logger.warning(f"[RELOAD] Attempting to reinitialize tier: {tier_name}")

        self.failure_counts[tier_name] += 1

        if self.failure_counts[tier_name] >= self.max_failures_before_alert:
            logger.critical(
                f"[CRITICAL] Tier '{tier_name}' has failed {self.failure_counts[tier_name]} times. "
                f"Manual intervention may be required."
            )

        try:
            if tier_name == "predictor":
                # Use AutoGluon ensemble predictor (unified with API)
                from src.ml.inference.ensemble_prediction_service import EnsemblePredictionService
                self.engine.predictor = EnsemblePredictionService(
                    nn_model_path="models/DISABLED_neural_network.pt",
                    autogluon_path="models/autogluon_ensemble"
                )
                logger.info("Tier 2 (AutoGluon Ensemble Predictor) reinitialized - unified with API")

            elif tier_name == "aether_engine":
                from src.risk.aether_engine import AetherRiskEngine
                self.engine.aether_engine = AetherRiskEngine(self.engine.db)
                logger.info("Tier 3 (Aether Risk Engine) reinitialized")

            elif tier_name == "strategic_layer":
                from src.llm.strategy.strategic_execution import StrategicExecutionLayer
                self.engine.strategic_layer = StrategicExecutionLayer(self.engine.db)
                logger.info("Tier 4 (LLM Strategic Layer) reinitialized")

            elif tier_name == "portfolio_risk_manager":
                from src.portfolio.risk.portfolio_risk_manager import PortfolioRiskManager
                self.engine.portfolio_risk_manager = PortfolioRiskManager(self.engine.db)
                logger.info("Tier 5 (Portfolio Risk Manager) reinitialized")

            elif tier_name == "position_manager":
                from src.portfolio.positions.position_manager import PositionManager
                self.engine.position_manager = PositionManager(
                    self.engine.db,
                    trading_client=self.engine._get_trading_client()
                )
                logger.info("Tier 5 (Position Manager) reinitialized")

            elif tier_name == "candle_generator":
                # DEPRECATED: LiveCandleGenerator replaced by VALRCandlePoller (October 2025)
                # This recovery path is kept for backwards compatibility but should not be used
                logger.warning(
                    "DEPRECATED: 'candle_generator' tier recovery is deprecated. "
                    "Use 'candle_poller' and 'websocket_client' instead."
                )

                # For backwards compatibility, reinitialize both poller and WebSocket
                import asyncpg
                from config.settings import settings
                from src.data.collectors.valr_candle_poller import VALRCandlePoller
                from src.data.collectors.valr_websocket_client import VALRWebSocketClient

                # Create asyncpg connection
                db_conn = await asyncpg.connect(
                    host=settings.database.postgres_host,
                    port=settings.database.postgres_port,
                    user=settings.database.postgres_user,
                    password=settings.database.postgres_password,
                    database=settings.database.postgres_db
                )

                # Reinitialize candle poller
                self.engine.candle_poller = VALRCandlePoller(
                    db=db_conn,
                    pairs=self.engine.pairs,
                    event_queue=self.engine.event_queue
                )
                asyncio.create_task(self.engine.candle_poller.start())

                # Reinitialize WebSocket client for real-time prices
                def on_price_update(tick):
                    event = {
                        'type': 'PRICE_UPDATE',
                        'pair': tick.pair,
                        'price': tick.price,
                        'timestamp': tick.timestamp.isoformat()
                    }
                    try:
                        self.engine.event_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning(f"Event queue full, dropping price update for {tick.pair}")

                self.engine.websocket_client = VALRWebSocketClient(
                    pairs=self.engine.pairs,
                    on_trade=on_price_update
                )
                asyncio.create_task(self.engine.websocket_client.start())

                logger.info("Tier 1 (VALRCandlePoller + WebSocket) reinitialized")

            else:
                logger.error(f"Unknown tier name: {tier_name}")
                return False

            self.tier_health[tier_name] = True
            logger.info(f"[OK] Tier '{tier_name}' reinitialized successfully")

            # Reset failure count on successful reinitialization
            self.failure_counts[tier_name] = 0

            return True

        except Exception as e:
            logger.error(
                f"[FAIL] Failed to reinitialize tier '{tier_name}': {e}",
                exc_info=True
            )
            self.tier_health[tier_name] = False
            return False

    def mark_tier_unhealthy(self, tier_name: str):
        """Mark a tier as unhealthy."""
        if tier_name in self.tier_health:
            self.tier_health[tier_name] = False
            logger.warning(f"[WARN] Tier '{tier_name}' marked as unhealthy")

    def mark_tier_healthy(self, tier_name: str):
        """Mark a tier as healthy."""
        if tier_name in self.tier_health:
            self.tier_health[tier_name] = True
            self.failure_counts[tier_name] = 0
            logger.info(f"[OK] Tier '{tier_name}' marked as healthy")

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of all tiers.

        Returns:
            Dict with health status and failure counts
        """
        return {
            "tier_health": self.tier_health.copy(),
            "failure_counts": self.failure_counts.copy(),
            "all_healthy": all(self.tier_health.values()),
            "unhealthy_tiers": [
                tier for tier, healthy in self.tier_health.items() if not healthy
            ]
        }

    def reset_all_health(self):
        """Reset all tier health statuses to healthy."""
        for tier in self.tier_health.keys():
            self.tier_health[tier] = True
            self.failure_counts[tier] = 0

        logger.info("All tier health statuses reset to healthy")


# Example usage and testing
if __name__ == "__main__":
    async def test_recovery_managers():
        """Test recovery managers."""
        print("\n" + "=" * 80)
        print("ERROR RECOVERY SYSTEM TEST")
        print("=" * 80 + "\n")

        # Test 1: WebSocket Recovery
        print("TEST 1: WebSocket Recovery Manager")
        print("-" * 80)

        ws_recovery = WebSocketRecoveryManager(max_retries=3)

        async def mock_connect():
            """Mock connection function that succeeds on 2nd attempt."""
            if ws_recovery.retry_count == 0:
                raise Exception("Connection failed (mock)")
            # Succeed on retry

        async def on_success():
            print("[OK] Reconnection successful callback triggered")

        result = await ws_recovery.reconnect_with_backoff(
            mock_connect,
            on_success=on_success
        )

        print(f"Reconnection result: {result}")
        print(f"Stats: {ws_recovery.get_stats()}")
        print()

        # Test 2: Rate Limiting
        print("TEST 2: Rate Limit Handler")
        print("-" * 80)

        rate_limiter = RateLimitHandler(max_requests_per_minute=5)

        print("Making 6 rapid requests (should trigger wait on 6th)...")

        for i in range(6):
            await rate_limiter.wait_if_rate_limited()
            print(f"Request {i+1} completed")

        print(f"Stats: {rate_limiter.get_stats()}")
        print()

        print("=" * 80)
        print("ERROR RECOVERY SYSTEM TEST COMPLETE")
        print("=" * 80)

    asyncio.run(test_recovery_managers())
