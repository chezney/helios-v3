"""
Helios Trading System V3.0 - Modularity API Router
API endpoints for modular architecture management
Following MODULAR_ARCHITECTURE_GUIDE.md specification
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.core import (
    module_loader,
    feature_flags,
    circuit_breaker_manager,
    module_testing_manager,
    RolloutStrategy,
)
from src.utils.logger import get_logger

logger = get_logger(__name__, component="api")

router = APIRouter(prefix="/api/modularity", tags=["Modularity"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class ModuleRegisterRequest(BaseModel):
    """Request to register a module"""
    name: str = Field(..., description="Module identifier")
    module_path: str = Field(..., description="Python import path")
    version: str = Field(..., description="Version string")
    dependencies: Optional[List[str]] = Field(default=None, description="Module dependencies")
    hot_reloadable: bool = Field(default=True, description="Whether module can be hot-reloaded")


class ModuleSwapRequest(BaseModel):
    """Request to swap module version"""
    name: str = Field(..., description="Module name")
    new_version_path: str = Field(..., description="New module path")
    rollback_on_failure: bool = Field(default=True, description="Rollback on failure")


class FeatureFlagCreateRequest(BaseModel):
    """Request to create feature flag"""
    name: str = Field(..., description="Feature flag name")
    enabled: bool = Field(default=False, description="Whether flag is enabled")
    strategy: RolloutStrategy = Field(default=RolloutStrategy.PERCENTAGE)
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Rollout percentage")
    metadata: Optional[Dict[str, Any]] = None


class FeatureFlagUpdateRequest(BaseModel):
    """Request to update feature flag"""
    enabled: Optional[bool] = None
    percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class WhitelistRequest(BaseModel):
    """Request to add/remove from whitelist"""
    user_id: str = Field(..., description="User identifier")


class CircuitBreakerCreateRequest(BaseModel):
    """Request to create circuit breaker"""
    name: str = Field(..., description="Circuit breaker name")
    failure_threshold: int = Field(default=5, ge=1, description="Failures before opening")
    success_threshold: int = Field(default=2, ge=1, description="Successes before closing")
    timeout_seconds: int = Field(default=60, ge=1, description="Timeout in open state")
    rolling_window_seconds: int = Field(default=60, ge=1, description="Failure counting window")


# ============================================================
# MODULE MANAGEMENT ENDPOINTS
# ============================================================

@router.post("/modules/register", status_code=status.HTTP_201_CREATED)
async def register_module(request: ModuleRegisterRequest):
    """
    Register a new module for loading.

    Example:
    ```json
    {
        "name": "neural_predictor_v2",
        "module_path": "src.ml.inference.neural_predictor_v2",
        "version": "2.0.0",
        "dependencies": ["feature_engineer"],
        "hot_reloadable": true
    }
    ```
    """
    try:
        await module_loader.register_module(
            name=request.name,
            module_path=request.module_path,
            version=request.version,
            dependencies=request.dependencies,
            hot_reloadable=request.hot_reloadable
        )

        logger.info(f"Module registered via API: {request.name}")

        return {
            "status": "success",
            "message": f"Module {request.name} registered successfully",
            "module": module_loader.get_module_status(request.name)
        }
    except Exception as e:
        logger.error(f"Failed to register module {request.name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register module: {str(e)}"
        )


@router.post("/modules/{name}/load")
async def load_module(name: str, force_reload: bool = False):
    """
    Load a registered module.

    Set force_reload=true to reload an already loaded module.
    """
    try:
        instance = await module_loader.load_module(name, force_reload=force_reload)

        logger.info(f"Module loaded via API: {name} (force_reload={force_reload})")

        return {
            "status": "success",
            "message": f"Module {name} loaded successfully",
            "module": module_loader.get_module_status(name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to load module {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load module: {str(e)}"
        )


@router.post("/modules/{name}/unload")
async def unload_module(name: str):
    """Unload a module"""
    try:
        success = await module_loader.unload_module(name)

        if success:
            logger.info(f"Module unloaded via API: {name}")
            return {
                "status": "success",
                "message": f"Module {name} unloaded successfully"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to unload module {name}"
            )
    except Exception as e:
        logger.error(f"Failed to unload module {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unload module: {str(e)}"
        )


@router.post("/modules/swap")
async def swap_module(request: ModuleSwapRequest):
    """
    Hot-swap a module with a new version.

    Example:
    ```json
    {
        "name": "neural_predictor",
        "new_version_path": "src.ml.inference.neural_predictor_v2",
        "rollback_on_failure": true
    }
    ```
    """
    try:
        success = await module_loader.swap_module(
            name=request.name,
            new_version_path=request.new_version_path,
            rollback_on_failure=request.rollback_on_failure
        )

        if success:
            logger.info(f"Module swapped via API: {request.name} → {request.new_version_path}")
            return {
                "status": "success",
                "message": f"Module {request.name} swapped successfully",
                "module": module_loader.get_module_status(request.name)
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to swap module {request.name}"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to swap module {request.name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to swap module: {str(e)}"
        )


@router.get("/modules/{name}/status")
async def get_module_status(name: str):
    """Get status of a specific module"""
    status_info = module_loader.get_module_status(name)

    if "error" in status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=status_info["error"]
        )

    return status_info


@router.get("/modules")
async def get_all_modules():
    """Get status of all registered modules"""
    return module_loader.get_all_modules_status()


@router.post("/modules/{name}/test")
async def test_module(name: str):
    """
    Run tests for a module before deployment.

    Returns test results including pass/fail status.
    """
    try:
        # Get module instance
        instance = await module_loader.load_module(name)

        # Get or create tester
        tester = module_testing_manager.get_tester(name)
        if not tester:
            # Create default tester
            tester = module_testing_manager.create_tester(name, category="general")

        # Run tests
        result = await module_testing_manager.run_tests(name, instance)

        logger.info(
            f"Module tests completed via API: {name} - "
            f"{result.passed}/{result.total_tests} passed"
        )

        return {
            "module_name": result.module_name,
            "total_tests": result.total_tests,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "duration_ms": result.duration_ms,
            "all_passed": result.all_passed,
            "results": [
                {
                    "test_name": r.test_name,
                    "status": r.status.value,
                    "duration_ms": r.duration_ms,
                    "error": r.error
                }
                for r in result.results
            ]
        }
    except Exception as e:
        logger.error(f"Failed to test module {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test module: {str(e)}"
        )


# ============================================================
# FEATURE FLAG ENDPOINTS
# ============================================================

@router.post("/feature-flags", status_code=status.HTTP_201_CREATED)
async def create_feature_flag(request: FeatureFlagCreateRequest):
    """
    Create a new feature flag.

    Example:
    ```json
    {
        "name": "new_trading_algorithm",
        "enabled": false,
        "strategy": "percentage",
        "percentage": 0.0,
        "metadata": {"description": "New algo for testing"}
    }
    ```
    """
    try:
        flag = await feature_flags.create_flag(
            name=request.name,
            enabled=request.enabled,
            strategy=request.strategy,
            percentage=request.percentage,
            metadata=request.metadata
        )

        logger.info(f"Feature flag created via API: {request.name}")

        return {
            "status": "success",
            "message": f"Feature flag {request.name} created successfully",
            "flag": feature_flags.get_flag_status(request.name)
        }
    except Exception as e:
        logger.error(f"Failed to create feature flag {request.name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create feature flag: {str(e)}"
        )


@router.get("/feature-flags/{name}")
async def get_feature_flag(name: str):
    """Get feature flag status"""
    status_info = feature_flags.get_flag_status(name)

    if "error" in status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=status_info["error"]
        )

    return status_info


@router.get("/feature-flags")
async def get_all_feature_flags():
    """Get all feature flags"""
    flags = feature_flags.get_all_flags()
    return {
        name: feature_flags.get_flag_status(name)
        for name in flags.keys()
    }


@router.post("/feature-flags/{name}/enable")
async def enable_feature_flag(name: str):
    """Enable a feature flag (100% rollout)"""
    try:
        await feature_flags.set_enabled(name, True)
        logger.info(f"Feature flag enabled via API: {name}")

        return {
            "status": "success",
            "message": f"Feature flag {name} enabled",
            "flag": feature_flags.get_flag_status(name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/feature-flags/{name}/disable")
async def disable_feature_flag(name: str):
    """Disable a feature flag (0% rollout)"""
    try:
        await feature_flags.set_enabled(name, False)
        logger.info(f"Feature flag disabled via API: {name}")

        return {
            "status": "success",
            "message": f"Feature flag {name} disabled",
            "flag": feature_flags.get_flag_status(name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/feature-flags/{name}/percentage")
async def set_feature_flag_percentage(name: str, percentage: float):
    """
    Set rollout percentage for a feature flag.

    Percentage should be between 0 and 100.
    """
    try:
        await feature_flags.set_percentage(name, percentage)
        logger.info(f"Feature flag percentage set via API: {name} → {percentage}%")

        return {
            "status": "success",
            "message": f"Feature flag {name} set to {percentage}%",
            "flag": feature_flags.get_flag_status(name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/feature-flags/{name}/whitelist/add")
async def add_to_whitelist(name: str, request: WhitelistRequest):
    """Add user to feature whitelist"""
    try:
        await feature_flags.add_to_whitelist(name, request.user_id)
        logger.info(f"User added to whitelist via API: {request.user_id} → {name}")

        return {
            "status": "success",
            "message": f"User {request.user_id} added to whitelist for {name}"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/feature-flags/{name}/whitelist/remove")
async def remove_from_whitelist(name: str, request: WhitelistRequest):
    """Remove user from feature whitelist"""
    try:
        await feature_flags.remove_from_whitelist(name, request.user_id)
        logger.info(f"User removed from whitelist via API: {request.user_id} → {name}")

        return {
            "status": "success",
            "message": f"User {request.user_id} removed from whitelist for {name}"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/feature-flags/{name}/kill-switch")
async def activate_kill_switch(name: str):
    """
    Emergency disable a feature (kill switch).

    Immediately disables feature for all users.
    """
    try:
        await feature_flags.kill_switch(name)
        logger.warning(f"⚠️ Kill switch activated via API: {name}")

        return {
            "status": "success",
            "message": f"Kill switch activated for {name}",
            "flag": feature_flags.get_flag_status(name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/feature-flags/{name}/check")
async def check_feature_enabled(name: str, user_id: Optional[str] = None):
    """
    Check if feature is enabled for a user.

    Returns boolean indicating if feature should be shown to user.
    """
    enabled = await feature_flags.is_enabled(name, user_id=user_id)

    return {
        "flag_name": name,
        "user_id": user_id,
        "enabled": enabled
    }


# ============================================================
# CIRCUIT BREAKER ENDPOINTS
# ============================================================

@router.post("/circuit-breakers", status_code=status.HTTP_201_CREATED)
async def create_circuit_breaker(request: CircuitBreakerCreateRequest):
    """
    Create a new circuit breaker.

    Example:
    ```json
    {
        "name": "valr_api",
        "failure_threshold": 5,
        "success_threshold": 2,
        "timeout_seconds": 60,
        "rolling_window_seconds": 60
    }
    ```
    """
    try:
        breaker = await circuit_breaker_manager.create_breaker(
            name=request.name,
            failure_threshold=request.failure_threshold,
            success_threshold=request.success_threshold,
            timeout_seconds=request.timeout_seconds,
            rolling_window_seconds=request.rolling_window_seconds
        )

        logger.info(f"Circuit breaker created via API: {request.name}")

        return {
            "status": "success",
            "message": f"Circuit breaker {request.name} created successfully",
            "breaker": breaker.get_status()
        }
    except Exception as e:
        logger.error(f"Failed to create circuit breaker {request.name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create circuit breaker: {str(e)}"
        )


@router.get("/circuit-breakers/{name}")
async def get_circuit_breaker_status(name: str):
    """Get circuit breaker status"""
    breaker = circuit_breaker_manager.get_breaker(name)

    if not breaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker {name} not found"
        )

    return breaker.get_status()


@router.get("/circuit-breakers")
async def get_all_circuit_breakers():
    """Get status of all circuit breakers"""
    return circuit_breaker_manager.get_all_statuses()


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(name: str):
    """Reset circuit breaker to initial state"""
    breaker = circuit_breaker_manager.get_breaker(name)

    if not breaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker {name} not found"
        )

    await breaker.reset()
    logger.info(f"Circuit breaker reset via API: {name}")

    return {
        "status": "success",
        "message": f"Circuit breaker {name} reset successfully",
        "breaker": breaker.get_status()
    }


@router.post("/circuit-breakers/{name}/open")
async def force_open_circuit(name: str):
    """Manually open circuit breaker (emergency stop)"""
    breaker = circuit_breaker_manager.get_breaker(name)

    if not breaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker {name} not found"
        )

    await breaker.force_open()
    logger.warning(f"⚠️ Circuit breaker manually opened via API: {name}")

    return {
        "status": "success",
        "message": f"Circuit breaker {name} opened",
        "breaker": breaker.get_status()
    }


@router.post("/circuit-breakers/{name}/close")
async def force_close_circuit(name: str):
    """Manually close circuit breaker (override)"""
    breaker = circuit_breaker_manager.get_breaker(name)

    if not breaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker {name} not found"
        )

    await breaker.force_close()
    logger.warning(f"Circuit breaker manually closed via API: {name}")

    return {
        "status": "success",
        "message": f"Circuit breaker {name} closed",
        "breaker": breaker.get_status()
    }


# ============================================================
# SYSTEM STATUS
# ============================================================

@router.get("/status")
async def get_modularity_status():
    """Get complete modularity system status"""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "modules": module_loader.get_all_modules_status(),
        "feature_flags": {
            name: feature_flags.get_flag_status(name)
            for name in feature_flags.get_all_flags().keys()
        },
        "circuit_breakers": circuit_breaker_manager.get_all_statuses()
    }
