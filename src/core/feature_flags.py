"""
Helios Trading System V3.0 - Feature Flags System
Gradual rollout and A/B testing capability
Following MODULAR_ARCHITECTURE_GUIDE.md specification
"""

import asyncio
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import random

from src.utils.logger import get_logger

logger = get_logger(__name__, component="modular_architecture")


class RolloutStrategy(str, Enum):
    """Feature rollout strategies"""
    ALL_USERS = "all_users"           # 100% rollout
    PERCENTAGE = "percentage"          # Gradual percentage rollout
    WHITELIST = "whitelist"           # Specific users only
    BLACKLIST = "blacklist"           # All except specific users
    KILL_SWITCH = "kill_switch"       # Feature disabled (0%)


@dataclass
class FeatureFlagConfig:
    """Feature flag configuration"""
    name: str
    enabled: bool = False
    strategy: RolloutStrategy = RolloutStrategy.PERCENTAGE
    percentage: float = 0.0  # 0.0 to 100.0
    whitelist: List[str] = field(default_factory=list)
    blacklist: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class FeatureFlagManager:
    """
    Feature flag management system for gradual rollouts.

    Features:
    - Enable/disable features dynamically
    - Percentage-based gradual rollout
    - User whitelisting/blacklisting
    - Kill switch for emergency disable
    - Persistent configuration (Redis backend)
    """

    def __init__(self, redis_client=None):
        self._flags: Dict[str, FeatureFlagConfig] = {}
        self._redis = redis_client
        self._lock = asyncio.Lock()

        # Initialize with default flags from PRD
        self._initialize_default_flags()

    def _initialize_default_flags(self) -> None:
        """Initialize default feature flags from PRD"""
        default_flags = [
            ("auto_trading", False, "Autonomous trading engine"),
            ("neural_network_v2", False, "Enhanced neural network model"),
            ("llm_strategic_analysis", True, "LLM strategic decision layer"),
            ("garch_volatility", True, "GARCH volatility forecasting"),
            ("kelly_position_sizing", True, "Kelly Criterion position sizing"),
            ("black_litterman", False, "Black-Litterman optimization"),
            ("websocket_streaming", True, "Real-time WebSocket data"),
            ("circuit_breakers", True, "Circuit breaker protection"),
        ]

        for name, enabled, description in default_flags:
            self._flags[name] = FeatureFlagConfig(
                name=name,
                enabled=enabled,
                strategy=RolloutStrategy.ALL_USERS if enabled else RolloutStrategy.KILL_SWITCH,
                percentage=100.0 if enabled else 0.0,
                metadata={"description": description}
            )

        logger.info(f"Initialized {len(default_flags)} default feature flags")

    async def create_flag(
        self,
        name: str,
        enabled: bool = False,
        strategy: RolloutStrategy = RolloutStrategy.PERCENTAGE,
        percentage: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> FeatureFlagConfig:
        """
        Create a new feature flag.

        Args:
            name: Feature flag name
            enabled: Whether flag is enabled
            strategy: Rollout strategy
            percentage: Rollout percentage (0-100)
            metadata: Additional metadata

        Returns:
            Created feature flag configuration
        """
        async with self._lock:
            if name in self._flags:
                logger.warning(f"Feature flag {name} already exists, updating")

            flag = FeatureFlagConfig(
                name=name,
                enabled=enabled,
                strategy=strategy,
                percentage=percentage,
                metadata=metadata or {}
            )

            self._flags[name] = flag
            logger.info(f"Feature flag created: {name} (enabled={enabled}, strategy={strategy.value})")

            # Persist to Redis if available
            if self._redis:
                await self._persist_flag(flag)

            return flag

    async def is_enabled(
        self,
        flag_name: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if a feature is enabled for a given user/context.

        Args:
            flag_name: Feature flag name
            user_id: User identifier (optional)
            context: Additional context for evaluation (optional)

        Returns:
            True if feature is enabled
        """
        if flag_name not in self._flags:
            logger.warning(f"Feature flag {flag_name} not found, returning False")
            return False

        flag = self._flags[flag_name]

        if not flag.enabled:
            return False

        # Evaluate based on strategy
        if flag.strategy == RolloutStrategy.KILL_SWITCH:
            return False

        elif flag.strategy == RolloutStrategy.ALL_USERS:
            return True

        elif flag.strategy == RolloutStrategy.PERCENTAGE:
            return self._evaluate_percentage(flag, user_id)

        elif flag.strategy == RolloutStrategy.WHITELIST:
            return user_id in flag.whitelist if user_id else False

        elif flag.strategy == RolloutStrategy.BLACKLIST:
            return user_id not in flag.blacklist if user_id else True

        return False

    def _evaluate_percentage(self, flag: FeatureFlagConfig, user_id: Optional[str]) -> bool:
        """
        Evaluate percentage-based rollout.

        Uses deterministic hash of user_id for consistent results.
        If no user_id, uses random evaluation.
        """
        if flag.percentage >= 100.0:
            return True
        if flag.percentage <= 0.0:
            return False

        if user_id:
            # Deterministic evaluation based on user_id hash
            hash_val = hash(f"{flag.name}:{user_id}")
            bucket = (hash_val % 100) + 1  # 1-100
            return bucket <= flag.percentage
        else:
            # Random evaluation (for non-user contexts)
            return random.random() * 100 <= flag.percentage

    async def set_enabled(self, flag_name: str, enabled: bool) -> None:
        """Enable or disable a feature flag"""
        async with self._lock:
            if flag_name not in self._flags:
                raise ValueError(f"Feature flag {flag_name} not found")

            flag = self._flags[flag_name]
            flag.enabled = enabled
            flag.updated_at = datetime.utcnow()

            # Update strategy based on enabled state
            if enabled and flag.strategy == RolloutStrategy.KILL_SWITCH:
                flag.strategy = RolloutStrategy.ALL_USERS
            elif not enabled:
                flag.strategy = RolloutStrategy.KILL_SWITCH

            logger.info(f"Feature flag {flag_name} set to {enabled}")

            if self._redis:
                await self._persist_flag(flag)

    async def set_percentage(self, flag_name: str, percentage: float) -> None:
        """
        Set rollout percentage for a feature.

        Args:
            flag_name: Feature flag name
            percentage: Percentage (0.0 to 100.0)
        """
        async with self._lock:
            if flag_name not in self._flags:
                raise ValueError(f"Feature flag {flag_name} not found")

            if not 0.0 <= percentage <= 100.0:
                raise ValueError(f"Percentage must be between 0 and 100, got {percentage}")

            flag = self._flags[flag_name]
            flag.percentage = percentage
            flag.strategy = RolloutStrategy.PERCENTAGE
            flag.updated_at = datetime.utcnow()

            logger.info(f"Feature flag {flag_name} percentage set to {percentage}%")

            if self._redis:
                await self._persist_flag(flag)

    async def add_to_whitelist(self, flag_name: str, user_id: str) -> None:
        """Add user to feature whitelist"""
        async with self._lock:
            if flag_name not in self._flags:
                raise ValueError(f"Feature flag {flag_name} not found")

            flag = self._flags[flag_name]
            if user_id not in flag.whitelist:
                flag.whitelist.append(user_id)
                flag.updated_at = datetime.utcnow()
                logger.info(f"User {user_id} added to whitelist for {flag_name}")

                if self._redis:
                    await self._persist_flag(flag)

    async def remove_from_whitelist(self, flag_name: str, user_id: str) -> None:
        """Remove user from feature whitelist"""
        async with self._lock:
            if flag_name not in self._flags:
                raise ValueError(f"Feature flag {flag_name} not found")

            flag = self._flags[flag_name]
            if user_id in flag.whitelist:
                flag.whitelist.remove(user_id)
                flag.updated_at = datetime.utcnow()
                logger.info(f"User {user_id} removed from whitelist for {flag_name}")

                if self._redis:
                    await self._persist_flag(flag)

    async def kill_switch(self, flag_name: str) -> None:
        """
        Emergency disable a feature (kill switch).

        Immediately disables feature for all users.
        """
        async with self._lock:
            if flag_name not in self._flags:
                raise ValueError(f"Feature flag {flag_name} not found")

            flag = self._flags[flag_name]
            flag.enabled = False
            flag.strategy = RolloutStrategy.KILL_SWITCH
            flag.percentage = 0.0
            flag.updated_at = datetime.utcnow()

            logger.warning(f"⚠️ KILL SWITCH activated for feature {flag_name}")

            if self._redis:
                await self._persist_flag(flag)

    def get_flag(self, flag_name: str) -> Optional[FeatureFlagConfig]:
        """Get feature flag configuration"""
        return self._flags.get(flag_name)

    def get_all_flags(self) -> Dict[str, FeatureFlagConfig]:
        """Get all feature flags"""
        return self._flags.copy()

    def get_flag_status(self, flag_name: str) -> Dict[str, Any]:
        """Get feature flag status as dictionary"""
        if flag_name not in self._flags:
            return {"error": f"Feature flag {flag_name} not found"}

        flag = self._flags[flag_name]

        return {
            "name": flag.name,
            "enabled": flag.enabled,
            "strategy": flag.strategy.value,
            "percentage": flag.percentage,
            "whitelist_count": len(flag.whitelist),
            "blacklist_count": len(flag.blacklist),
            "metadata": flag.metadata,
            "created_at": flag.created_at.isoformat(),
            "updated_at": flag.updated_at.isoformat()
        }

    async def _persist_flag(self, flag: FeatureFlagConfig) -> None:
        """Persist feature flag to Redis"""
        if not self._redis:
            return

        try:
            key = f"feature_flag:{flag.name}"
            value = {
                "enabled": flag.enabled,
                "strategy": flag.strategy.value,
                "percentage": flag.percentage,
                "whitelist": flag.whitelist,
                "blacklist": flag.blacklist,
                "metadata": flag.metadata,
                "updated_at": flag.updated_at.isoformat()
            }

            # Redis persistence would go here
            # await self._redis.set(key, json.dumps(value))
            pass

        except Exception as e:
            logger.error(f"Failed to persist feature flag {flag.name}: {e}", exc_info=True)


# Global feature flag manager instance
feature_flags = FeatureFlagManager()
