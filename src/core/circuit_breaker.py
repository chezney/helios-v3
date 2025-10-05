"""
Helios Trading System V3.0 - Circuit Breaker System
Prevent cascading failures during module updates
Following MODULAR_ARCHITECTURE_GUIDE.md specification
"""

import asyncio
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import time

from src.utils.logger import get_logger

logger = get_logger(__name__, component="modular_architecture")


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    name: str
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open before closing
    timeout_seconds: int = 60   # Time in open state before half-open
    rolling_window_seconds: int = 60  # Time window for failure counting


@dataclass
class CircuitBreakerMetrics:
    """Circuit breaker metrics"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, all requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed

    Workflow:
    1. CLOSED → monitor failures
    2. If failures >= threshold → OPEN
    3. After timeout → HALF_OPEN
    4. If successes in HALF_OPEN >= threshold → CLOSED
    5. If failure in HALF_OPEN → OPEN
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()
        self._failure_timestamps: list[float] = []

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args, **kwargs: Function arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open
        """
        async with self._lock:
            self.metrics.total_requests += 1

            # Check circuit state
            if self.metrics.state == CircuitState.OPEN:
                # Check if timeout elapsed
                if self._should_attempt_reset():
                    logger.info(f"Circuit {self.config.name}: Entering HALF_OPEN state")
                    self.metrics.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker {self.config.name} is OPEN"
                    )

        # Execute function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self) -> None:
        """Handle successful request"""
        async with self._lock:
            self.metrics.total_successes += 1
            self.metrics.last_success_time = datetime.utcnow()

            if self.metrics.state == CircuitState.HALF_OPEN:
                self.metrics.success_count += 1
                logger.info(
                    f"Circuit {self.config.name}: Success in HALF_OPEN "
                    f"({self.metrics.success_count}/{self.config.success_threshold})"
                )

                # Check if we can close the circuit
                if self.metrics.success_count >= self.config.success_threshold:
                    await self._close_circuit()

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed request"""
        async with self._lock:
            now = time.time()
            self.metrics.total_failures += 1
            self.metrics.last_failure_time = datetime.utcnow()

            # Add to failure timestamps
            self._failure_timestamps.append(now)

            # Clean old failures outside rolling window
            cutoff = now - self.config.rolling_window_seconds
            self._failure_timestamps = [
                ts for ts in self._failure_timestamps if ts > cutoff
            ]

            self.metrics.failure_count = len(self._failure_timestamps)

            logger.warning(
                f"Circuit {self.config.name}: Failure recorded "
                f"({self.metrics.failure_count}/{self.config.failure_threshold}) - {error}"
            )

            # Check state transitions
            if self.metrics.state == CircuitState.HALF_OPEN:
                # Any failure in half-open -> back to open
                await self._open_circuit()
                logger.warning(f"Circuit {self.config.name}: Failed in HALF_OPEN, reopening circuit")

            elif self.metrics.state == CircuitState.CLOSED:
                # Check if threshold exceeded
                if self.metrics.failure_count >= self.config.failure_threshold:
                    await self._open_circuit()

    async def _open_circuit(self) -> None:
        """Open the circuit (block requests)"""
        self.metrics.state = CircuitState.OPEN
        self.metrics.opened_at = datetime.utcnow()
        self.metrics.success_count = 0

        logger.error(
            f"⚠️ Circuit breaker {self.config.name} OPENED - "
            f"Failures: {self.metrics.failure_count}/{self.config.failure_threshold}"
        )

    async def _close_circuit(self) -> None:
        """Close the circuit (allow requests)"""
        self.metrics.state = CircuitState.CLOSED
        self.metrics.failure_count = 0
        self.metrics.success_count = 0
        self._failure_timestamps.clear()

        logger.info(f"✓ Circuit breaker {self.config.name} CLOSED - Service recovered")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.metrics.opened_at:
            return False

        elapsed = datetime.utcnow() - self.metrics.opened_at
        return elapsed.total_seconds() >= self.config.timeout_seconds

    async def force_open(self) -> None:
        """Manually open the circuit (emergency stop)"""
        async with self._lock:
            await self._open_circuit()
            logger.warning(f"Circuit breaker {self.config.name} manually opened")

    async def force_close(self) -> None:
        """Manually close the circuit (override)"""
        async with self._lock:
            await self._close_circuit()
            logger.warning(f"Circuit breaker {self.config.name} manually closed")

    async def reset(self) -> None:
        """Reset circuit breaker to initial state"""
        async with self._lock:
            self.metrics = CircuitBreakerMetrics()
            self._failure_timestamps.clear()
            logger.info(f"Circuit breaker {self.config.name} reset")

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        return {
            "name": self.config.name,
            "state": self.metrics.state.value,
            "failure_count": self.metrics.failure_count,
            "success_count": self.metrics.success_count,
            "total_requests": self.metrics.total_requests,
            "total_failures": self.metrics.total_failures,
            "total_successes": self.metrics.total_successes,
            "failure_rate": (
                self.metrics.total_failures / self.metrics.total_requests * 100
                if self.metrics.total_requests > 0
                else 0.0
            ),
            "last_failure": (
                self.metrics.last_failure_time.isoformat()
                if self.metrics.last_failure_time
                else None
            ),
            "last_success": (
                self.metrics.last_success_time.isoformat()
                if self.metrics.last_success_time
                else None
            ),
            "opened_at": (
                self.metrics.opened_at.isoformat() if self.metrics.opened_at else None
            ),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "rolling_window_seconds": self.config.rolling_window_seconds,
            },
        }


class CircuitBreakerManager:
    """
    Manage multiple circuit breakers.

    Provides centralized management of circuit breakers for different services.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def create_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
        rolling_window_seconds: int = 60,
    ) -> CircuitBreaker:
        """
        Create a new circuit breaker.

        Args:
            name: Circuit breaker name
            failure_threshold: Failures before opening
            success_threshold: Successes in half-open before closing
            timeout_seconds: Time in open state
            rolling_window_seconds: Time window for failure counting

        Returns:
            Created circuit breaker
        """
        async with self._lock:
            if name in self._breakers:
                logger.warning(f"Circuit breaker {name} already exists")
                return self._breakers[name]

            config = CircuitBreakerConfig(
                name=name,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout_seconds=timeout_seconds,
                rolling_window_seconds=rolling_window_seconds,
            )

            breaker = CircuitBreaker(config)
            self._breakers[name] = breaker

            logger.info(f"Circuit breaker created: {name}")
            return breaker

    async def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        """Get existing circuit breaker or create new one"""
        if name in self._breakers:
            return self._breakers[name]
        return await self.create_breaker(name, **kwargs)

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self._breakers.get(name)

    async def remove_breaker(self, name: str) -> bool:
        """Remove circuit breaker"""
        async with self._lock:
            if name in self._breakers:
                del self._breakers[name]
                logger.info(f"Circuit breaker removed: {name}")
                return True
            return False

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers"""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    async def reset_all(self) -> None:
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            await breaker.reset()
        logger.info("All circuit breakers reset")


# Global circuit breaker manager instance
circuit_breaker_manager = CircuitBreakerManager()
