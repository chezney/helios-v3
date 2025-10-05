"""
Health Check Router

Provides system health monitoring endpoints.
"""

from datetime import datetime
from typing import Dict, Any
import asyncpg

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config.settings import settings
from src.api.dependencies import get_postgres_connection, get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__, component="health_check")

router = APIRouter(prefix="/api", tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: str
    version: str
    environment: str
    services: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Complete system health check

    Checks:
    - API status
    - Database connections (PostgreSQL, Redis)
    - Configuration

    Returns:
        HealthResponse with status of all services
    """
    services = {
        "api": {"status": "healthy", "message": "API operational"}
    }

    # Check PostgreSQL
    try:
        from src.api.dependencies import _db_provider
        pool = await _db_provider.get_postgres_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            services["postgresql"] = {
                "status": "healthy",
                "host": settings.database.postgres_host,
                "database": settings.database.postgres_db,
                "version": version.split(',')[0]
            }
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        services["postgresql"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Redis
    try:
        from src.api.dependencies import _db_provider
        redis = await _db_provider.get_redis_client()
        await redis.ping()
        info = await redis.info()
        services["redis"] = {
            "status": "healthy",
            "host": settings.database.redis_host,
            "version": info.get("redis_version", "unknown")
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        services["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Determine overall status
    overall_status = "healthy"
    if any(s.get("status") == "unhealthy" for s in services.values()):
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        version="3.0.0",
        environment=settings.environment.value,
        services=services
    )


@router.get("/health/live")
async def liveness_probe():
    """
    Kubernetes liveness probe

    Simple check that the API is running.
    Returns 200 if alive, 503 if not.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe():
    """
    Kubernetes readiness probe

    Checks if the API is ready to accept traffic.
    Verifies database connectivity.
    """
    try:
        from src.api.dependencies import _db_provider
        pool = await _db_provider.get_postgres_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return {"status": "ready"}

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service not ready - database connection failed"
        )


@router.get("/health/config")
async def config_check():
    """
    Configuration health check

    Returns current system configuration (non-sensitive info only).
    """
    return {
        "environment": settings.environment.value,
        "trading_mode": settings.trading.mode.value,
        "trading_pairs": settings.trading.trading_pairs,
        "database": {
            "postgres_host": settings.database.postgres_host,
            "postgres_db": settings.database.postgres_db,
            "redis_host": settings.database.redis_host
        },
        "ml": {
            "device": settings.ml.device,
            "model_path": settings.ml.model_path
        },
        "llm": {
            "provider": settings.llm.provider,
            "model": settings.llm.anthropic_model
        },
        "feature_flags": {
            "auto_trading": settings.enable_auto_trading,
            "websocket": settings.enable_websocket,
            "ml_predictions": settings.enable_ml_predictions,
            "llm_analysis": settings.enable_llm_analysis
        }
    }
