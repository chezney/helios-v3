"""
Helios Trading System V3.0 - Main Application Entry Point
FastAPI application with modular architecture, 5-tier system, and complete lifecycle management
Following PRD and CLAUDE.md specifications
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from config.settings import settings
from src.utils.logger import setup_logging, get_logger
from src.api.dependencies import initialize_services, cleanup_services
from src.core import module_loader, feature_flags, circuit_breaker_manager

# Import API routers
from src.api.routers import modularity_router

# Setup logging
setup_logging(
    log_level=settings.logging.level,
    log_format=settings.logging.format,
    log_dir=settings.logging.log_dir
)

logger = get_logger(__name__, component="api")


# ============================================================
# APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown.

    Startup sequence:
    1. Initialize databases (PostgreSQL, Redis, InfluxDB)
    2. Initialize modular architecture
    3. Register default circuit breakers
    4. Load pre-configured modules
    5. Start background tasks

    Shutdown sequence:
    1. Stop background tasks
    2. Close database connections
    3. Cleanup resources
    """
    logger.info("=" * 60)
    logger.info("🚀 Starting Helios Trading System V3.0")
    logger.info("=" * 60)

    try:
        # Initialize all database services
        logger.info("Initializing database services...")
        await initialize_services()
        logger.info("✓ Database services initialized")

        # Initialize modular architecture
        logger.info("Initializing modular architecture...")
        await initialize_modular_architecture()
        logger.info("✓ Modular architecture initialized")

        # Log system configuration
        logger.info(f"Environment: {settings.environment.value}")
        logger.info(f"Trading Mode: {settings.trading.mode.value}")
        logger.info(f"Auto-trading: {'ENABLED' if settings.enable_auto_trading else 'DISABLED'}")
        logger.info(f"ML Predictions: {'ENABLED' if settings.enable_ml_predictions else 'DISABLED'}")
        logger.info(f"LLM Analysis: {'ENABLED' if settings.enable_llm_analysis else 'DISABLED'}")

        logger.info("=" * 60)
        logger.info("✓ Helios Trading System V3.0 is ready")
        logger.info("=" * 60)

        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise
    finally:
        # Shutdown
        logger.info("=" * 60)
        logger.info("🛑 Shutting down Helios Trading System V3.0")
        logger.info("=" * 60)

        try:
            await cleanup_services()
            logger.info("✓ Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

        logger.info("=" * 60)
        logger.info("Helios Trading System V3.0 shutdown complete")
        logger.info("=" * 60)


async def initialize_modular_architecture():
    """Initialize modular architecture components"""

    # Register default circuit breakers for critical services
    logger.info("Registering default circuit breakers...")

    critical_services = [
        ("valr_api", 5, 2, 60, 60),
        ("postgres_db", 10, 3, 30, 60),
        ("redis_cache", 10, 3, 30, 60),
        ("neural_network", 3, 2, 120, 120),
        ("llm_api", 5, 2, 60, 60),
    ]

    for name, fail_thresh, success_thresh, timeout, window in critical_services:
        await circuit_breaker_manager.create_breaker(
            name=name,
            failure_threshold=fail_thresh,
            success_threshold=success_thresh,
            timeout_seconds=timeout,
            rolling_window_seconds=window
        )
        logger.info(f"  ✓ Circuit breaker created: {name}")

    # Log feature flag status
    logger.info("Feature flags status:")
    all_flags = feature_flags.get_all_flags()
    for flag_name, flag_config in all_flags.items():
        status = "ENABLED" if flag_config.enabled else "DISABLED"
        logger.info(f"  - {flag_name}: {status} ({flag_config.strategy.value})")


# ============================================================
# CREATE APPLICATION
# ============================================================

app = FastAPI(
    title="Helios Trading System V3.0",
    description=(
        "Advanced cryptocurrency trading system with 5-tier architecture:\n"
        "- Tier 1: Data Ingestion & Feature Engineering (90 features)\n"
        "- Tier 2: 40M Parameter Neural Network\n"
        "- Tier 3: Aether Dynamic Leverage Engine (GARCH + Kelly Criterion)\n"
        "- Tier 4: LLM Strategic Execution Layer (Claude/GPT-4)\n"
        "- Tier 5: Guardian Portfolio Manager (MPT + Black-Litterman)\n\n"
        "Features modular architecture with hot-reload, feature flags, and circuit breakers."
    ),
    version="3.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)


# ============================================================
# MIDDLEWARE
# ============================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing"""
    start_time = asyncio.get_event_loop().time()

    # Log request
    logger.info(f"→ {request.method} {request.url.path}")

    try:
        response = await call_next(request)

        # Calculate duration
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        # Log response
        logger.info(
            f"← {request.method} {request.url.path} "
            f"[{response.status_code}] {duration_ms:.2f}ms"
        )

        # Add timing header
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        return response

    except Exception as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        logger.error(
            f"✗ {request.method} {request.url.path} "
            f"failed after {duration_ms:.2f}ms: {e}",
            exc_info=True
        )
        raise


# ============================================================
# EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.is_development else "An error occurred",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================
# ROOT ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Root endpoint with system information"""
    return {
        "name": "Helios Trading System",
        "version": "3.1.0",
        "status": "operational",
        "environment": settings.environment.value,
        "trading_mode": settings.trading.mode.value,
        "features": {
            "auto_trading": settings.enable_auto_trading,
            "ml_predictions": settings.enable_ml_predictions,
            "llm_analysis": settings.enable_llm_analysis,
            "websocket_streaming": settings.enable_websocket,
        },
        "architecture": {
            "tier1": "Data Ingestion & Feature Engineering",
            "tier2": "40M Parameter Neural Network",
            "tier3": "Aether Dynamic Leverage Engine",
            "tier4": "LLM Strategic Execution Layer",
            "tier5": "Guardian Portfolio Manager",
        },
        "modular_architecture": {
            "hot_reload": True,
            "feature_flags": True,
            "circuit_breakers": True,
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "3.1.0"
    }


@app.get("/api/system/info")
async def system_info():
    """Detailed system information"""
    return {
        "version": "3.1.0",
        "environment": settings.environment.value,
        "trading_mode": settings.trading.mode.value,
        "platform": sys.platform,
        "python_version": sys.version,
        "configuration": {
            "trading_pairs": settings.trading.trading_pairs,
            "max_leverage": settings.trading.max_leverage,
            "max_drawdown_pct": settings.trading.max_drawdown_pct,
            "daily_loss_limit_pct": settings.trading.daily_loss_limit_pct,
        },
        "ml_config": {
            "device": settings.ml.device,
            "batch_size": settings.ml.batch_size,
            "mixed_precision": settings.ml.mixed_precision,
            "gradient_checkpointing": settings.ml.gradient_checkpointing,
        },
        "llm_config": {
            "provider": settings.llm.provider,
            "model": (
                settings.llm.anthropic_model
                if settings.llm.provider == "anthropic"
                else settings.llm.openai_model
            ),
            "temperature": settings.llm.temperature,
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================
# REGISTER ROUTERS
# ============================================================

# Modular architecture management
app.include_router(modularity_router)

# TODO: Add remaining routers as they are implemented
# app.include_router(tier1_data_router)
# app.include_router(tier2_ml_router)
# app.include_router(tier3_risk_router)
# app.include_router(tier4_llm_router)
# app.include_router(tier5_portfolio_router)
# app.include_router(trading_router)
# app.include_router(market_router)
# app.include_router(analytics_router)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    logger.info("Starting Helios Trading System V3.0 via uvicorn")

    uvicorn.run(
        "main_v3:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.logging.level.lower(),
        access_log=True,
    )
