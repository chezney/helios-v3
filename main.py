"""
Helios Trading System V3.0 - Main Application Entry Point

FastAPI application with clean architecture following PRD specifications.
Phase: Tier 1 (Data Foundation) complete, adding orchestration layer.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# Configuration
from config.settings import settings
from src.utils.logger import setup_logging, get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__, component="main_application")


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 80)
    logger.info("  HELIOS TRADING SYSTEM V3.0")
    logger.info("  Starting application...")
    logger.info("=" * 80)
    logger.info(f"  Environment: {settings.environment}")
    logger.info(f"  Trading Mode: {settings.trading.mode}")
    logger.info(f"  Pairs: {settings.trading.trading_pairs}")
    logger.info(f"  Database: {settings.database.postgres_host}:{settings.database.postgres_port}")
    logger.info("=" * 80)

    # Verify database connection
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )
        logger.info("[OK] Database connection verified")
        await conn.close()
    except Exception as e:
        logger.error(f"[ERROR] Database connection failed: {e}")
        raise

    logger.info("")
    logger.info("Application startup complete. Ready to accept requests.")
    logger.info("=" * 80)

    yield

    # Shutdown
    logger.info("=" * 80)
    logger.info("  HELIOS TRADING SYSTEM V3.0")
    logger.info("  Shutting down application...")
    logger.info("=" * 80)
    logger.info("Application shutdown complete.")
    logger.info("=" * 80)


# Create FastAPI application
app = FastAPI(
    title="Helios Trading System V3.0",
    description="Autonomous cryptocurrency trading system with 5-tier architecture",
    version="3.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "Validation error",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "message": str(exc) if settings.is_development else "An error occurred"
        }
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Helios Trading System V3.0",
        "version": "3.0.0",
        "status": "operational",
        "tier": "Tier 1 (Data Foundation) Complete",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/api/health",
            "docs": "/docs",
            "tier1_control": "/api/tier1/*"
        }
    }


# Import and mount routers
# Note: Only importing routers that exist. Others will be added as we build them.

# Health check router (will create)
try:
    from src.api.routers.health import router as health_router
    app.include_router(health_router)
    logger.info("✓ Mounted health router")
except ImportError as e:
    logger.warning(f"Health router not available yet: {e}")

# Tier 1 data collection control router (will create)
try:
    from src.api.routers.tier1 import router as tier1_router
    app.include_router(tier1_router)
    logger.info("✓ Mounted Tier 1 router")
except ImportError as e:
    logger.warning(f"Tier 1 router not available yet: {e}")

# Modularity router (exists from v3.1.0)
try:
    from src.api.routers.modularity import router as modularity_router
    app.include_router(modularity_router)
    logger.info("✓ Mounted modularity router")
except ImportError as e:
    logger.warning(f"Modularity router not available: {e}")


if __name__ == "__main__":
    # Development server
    # In production, use: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
