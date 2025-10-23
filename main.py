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
from fastapi.responses import JSONResponse, FileResponse
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
    # NOTE: Skipping startup verification - connection pools handle this better
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db,
            ssl=False  # Disable SSL for localhost Docker PostgreSQL
        )
        logger.info("[OK] Database connection verified")
        await conn.close()
    except Exception as e:
        logger.warning(f"[SKIP] Database verification failed (will retry via connection pools): {e}")
        # Don't raise - let connection pools handle it

    # Initialize Tier 2 prediction service
    try:
        from src.api.routers.tier2 import init_prediction_service
        init_prediction_service()
        logger.info("[OK] Tier 2 prediction service initialized")
    except Exception as e:
        logger.warning(f"[SKIP] Tier 2 prediction service not available: {e}")

    # Initialize Tier 3 Aether Risk Engine
    try:
        from src.risk.aether_engine import init_aether_engine
        init_aether_engine()
        logger.info("[OK] Tier 3 Aether Risk Engine initialized")
    except Exception as e:
        logger.warning(f"[SKIP] Tier 3 Aether Risk Engine not available: {e}")

    # Initialize Tier 4 LLM Strategic Layer
    try:
        import os
        llm_provider = os.getenv('LLM_PROVIDER', 'anthropic')
        logger.info(f"[OK] Tier 4 LLM Strategic Layer configured (provider: {llm_provider})")
    except Exception as e:
        logger.warning(f"[SKIP] Tier 4 LLM Strategic Layer not available: {e}")

    # Initialize Tier 5 Portfolio Manager
    try:
        # Verify portfolio state exists
        import asyncpg
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db,
            ssl=False  # Disable SSL for localhost Docker PostgreSQL
        )
        result = await conn.fetchval("SELECT COUNT(*) FROM portfolio_state")
        if result == 0:
            await conn.execute("""
                INSERT INTO portfolio_state (total_value_zar, peak_value_zar, current_drawdown_pct, max_drawdown_pct, last_updated)
                VALUES (100000.00, 100000.00, 0.0, 0.0, NOW())
            """)
            logger.info("[OK] Tier 5 Portfolio Manager initialized with R100,000")
        else:
            logger.info("[OK] Tier 5 Portfolio Manager initialized (existing portfolio found)")
        await conn.close()
    except Exception as e:
        logger.warning(f"[SKIP] Tier 5 Portfolio Manager initialization: {e}")
        # Don't raise - portfolio manager can connect later via connection pool

    # Tier 1 WebSocket Data Collection - Managed by Autonomous Engine
    # NOTE: DO NOT auto-start WebSocket here - use Autonomous Engine API instead
    # Start data collection: POST /api/autonomous-engine/start
    # Stop data collection:  POST /api/autonomous-engine/stop
    # Check status:          GET  /api/autonomous-engine/status
    logger.info("")
    logger.info("[Tier 1] WebSocket data collection ready (managed by Autonomous Engine)")
    logger.info("[INFO] Start via API: POST /api/autonomous-engine/start")

    # Initialize Alert System (Phase 7)
    try:
        from src.alerts.alert_manager import alert_manager
        from src.alerts.email_notifier import EmailNotifier
        from src.alerts.sms_notifier import SMSNotifier
        from src.alerts.alert_rules import setup_default_alert_rules

        # Add notification channels
        email_notifier = EmailNotifier()
        if email_notifier.enabled:
            alert_manager.add_notifier(email_notifier)
            logger.info("[OK] Email notifications enabled")
        else:
            logger.warning("[SKIP] Email notifications disabled (not configured)")

        sms_notifier = SMSNotifier()
        if sms_notifier.enabled:
            alert_manager.add_notifier(sms_notifier)
            logger.info("[OK] SMS notifications enabled")
        else:
            logger.warning("[SKIP] SMS notifications disabled (not configured)")

        # Setup default alert rules
        setup_default_alert_rules()
        logger.info(f"[OK] Alert system initialized ({len(alert_manager.rules)} rules, {len(alert_manager.notifiers)} channels)")

        # Start alert checking loop
        async def alert_check_loop():
            while True:
                await alert_manager.check_all_rules()
                await asyncio.sleep(30)  # Check every 30 seconds

        asyncio.create_task(alert_check_loop())
        logger.info("[OK] Alert checking loop started (30s interval)")

    except Exception as e:
        logger.warning(f"[SKIP] Alert system not available: {e}")

    # Initialize Candle Aggregator Service (Tier 1 - Data Foundation)
    try:
        from src.data.processors.candle_aggregator_service import CandleAggregatorService

        aggregator_service = CandleAggregatorService(
            pairs=settings.trading.trading_pairs
        )

        # Start background aggregation task
        asyncio.create_task(aggregator_service.start())
        logger.info(f"[OK] Candle aggregator service started (5m/15m/1h/4h/1d for {len(settings.trading.trading_pairs)} pairs)")

        # Store reference for access in routers
        app.state.candle_aggregator = aggregator_service

    except Exception as e:
        logger.warning(f"[SKIP] Candle aggregator service not available: {e}")

    logger.info("")
    logger.info("Application startup complete. Ready to accept requests.")
    logger.info("=" * 80)

    # Auto-start Autonomous Trading Engine
    # Note: We need to wait a moment for the server to be fully ready to accept HTTP requests
    async def auto_start_engine():
        """Auto-start the trading engine after a short delay"""
        await asyncio.sleep(2)  # Wait 2 seconds for server to be fully ready

        try:
            logger.info("")
            logger.info("[AUTO-START] Starting Autonomous Trading Engine...")

            # Import HTTP client to call the start endpoint
            import httpx
            async with httpx.AsyncClient() as client:
                # Prepare engine configuration
                engine_config = {
                    "trading_mode": settings.trading.mode.value,  # "PAPER" or "LIVE"
                    "pairs": settings.trading.trading_pairs,  # ["BTCZAR", "ETHZAR", "SOLZAR"]
                    "auto_trading_enabled": True  # Enable autonomous trading on startup
                }

                response = await client.post(
                    "http://localhost:8100/api/autonomous-engine/start",
                    json=engine_config,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"[OK] Autonomous Trading Engine started successfully")
                    logger.info(f"     Mode: {engine_config['trading_mode']}")
                    logger.info(f"     Pairs: {', '.join(engine_config['pairs'])}")
                    logger.info(f"     Auto-Trading: {engine_config['auto_trading_enabled']}")
                    logger.info("")
                else:
                    logger.warning(f"[WARN] Engine start returned status {response.status_code}: {response.text}")

        except Exception as e:
            logger.warning(f"[SKIP] Could not auto-start Autonomous Engine: {e}")
            logger.info("[INFO] You can start it manually: POST /api/autonomous-engine/start")

    # Schedule auto-start task
    asyncio.create_task(auto_start_engine())

    logger.info("")
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

# Rate Limiting Middleware
try:
    from src.api.middleware.rate_limiter import RateLimiter
    app.add_middleware(RateLimiter, requests_per_second=100)
    logger.info("✓ Rate limiting enabled (100 req/sec)")
except ImportError as e:
    logger.warning(f"Rate limiting not available: {e}")


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


# Root endpoint - Serve Dashboard (BTCZAR)
@app.get("/")
async def serve_dashboard():
    """Serve the BTCZAR trading dashboard HTML"""
    return FileResponse("dashboard.html")

# SOLZAR Dashboard endpoint
@app.get("/solzar")
async def serve_solzar_dashboard():
    """Serve the SOLZAR trading dashboard HTML"""
    return FileResponse("dashboard_solzar.html")

# ETHZAR Dashboard endpoint
@app.get("/ethzar")
async def serve_ethzar_dashboard():
    """Serve the ETHZAR trading dashboard HTML"""
    return FileResponse("dashboard_ethzar.html")

# Multi-Pair Dashboard endpoint
@app.get("/all")
async def serve_all_pairs_dashboard():
    """Serve the multi-pair overview dashboard HTML"""
    return FileResponse("dashboard_all.html")

# API info endpoint
@app.get("/api")
async def api_info():
    """API information"""
    return {
        "name": "Helios Trading System V3.0",
        "version": "3.0.0",
        "status": "operational",
        "tier": "Tier 1-5 Complete (Data + Neural Network + Risk + LLM Strategy + Portfolio Manager)",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "dashboard": "/",
            "health": "/api/health",
            "docs": "/docs",
            "tier1_control": "/api/tier1/*",
            "tier2_predictions": "/api/tier2/*",
            "tier3_risk_management": "/api/tier3/*",
            "tier4_llm_strategy": "/api/tier4/*",
            "tier5_portfolio_manager": "/api/tier5/*"
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

# Tier 2 neural network router (Phase 2)
try:
    from src.api.routers.tier2 import router as tier2_router
    app.include_router(tier2_router)
    logger.info("✓ Mounted Tier 2 (Neural Network) router")
except ImportError as e:
    logger.warning(f"Tier 2 router not available: {e}")

# Tier 3 risk management router (Phase 3)
try:
    from src.api.routers.tier3 import router as tier3_router
    app.include_router(tier3_router)
    logger.info("✓ Mounted Tier 3 (Risk Management) router")
except ImportError as e:
    logger.warning(f"Tier 3 router not available: {e}")

# Tier 4 LLM strategic layer router (Phase 4)
try:
    from src.api.routers.tier4 import router as tier4_router
    app.include_router(tier4_router)
    logger.info("✓ Mounted Tier 4 (LLM Strategic) router")
except ImportError as e:
    logger.warning(f"Tier 4 router not available: {e}")

# Tier 5 portfolio manager router (Phase 5)
try:
    from src.api.routers.tier5 import router as tier5_router
    app.include_router(tier5_router)
    logger.info("✓ Mounted Tier 5 (Portfolio Manager) router")
except ImportError as e:
    logger.warning(f"Tier 5 router not available: {e}")

# WebSocket GUI router (Phase 7)
try:
    from src.api.routers.websocket_gui import router as websocket_gui_router
    app.include_router(websocket_gui_router)
    logger.info("✓ Mounted WebSocket GUI router (6 channels)")
except ImportError as e:
    logger.warning(f"WebSocket GUI router not available: {e}")

# Metrics router (Phase 7 - Prometheus)
try:
    from src.api.routers.metrics import router as metrics_router
    app.include_router(metrics_router)
    logger.info("✓ Mounted Prometheus metrics router (/metrics)")
except ImportError as e:
    logger.warning(f"Metrics router not available: {e}")

# Alerts router (Phase 7 - Alert System)
try:
    from src.api.routers.alerts import router as alerts_router
    app.include_router(alerts_router)
    logger.info("✓ Mounted Alert System router (/api/alerts)")
except ImportError as e:
    logger.warning(f"Alerts router not available: {e}")

# Portfolio router (Phase 7 - Portfolio Management API)
try:
    from src.api.routers.portfolio import router as portfolio_router
    app.include_router(portfolio_router)
    logger.info("✓ Mounted Portfolio Management router (/api/portfolio)")
except ImportError as e:
    logger.warning(f"Portfolio router not available: {e}")

# Trading router (Phase 7 - Trading Control API)
try:
    from src.api.routers.trading import router as trading_router
    app.include_router(trading_router)
    logger.info("✓ Mounted Trading Control router (/api/trading)")
except ImportError as e:
    logger.warning(f"Trading router not available: {e}")

# System router (Phase 7 - System Health API)
try:
    from src.api.routers.system import router as system_router
    app.include_router(system_router)
    logger.info("✓ Mounted System Health router (/api/system)")
except ImportError as e:
    logger.warning(f"System router not available: {e}")

# Market router (Phase 7 - Market Data API)
try:
    from src.api.routers.market import router as market_router
    app.include_router(market_router)
    logger.info("✓ Mounted Market Data router (/api/market)")
except ImportError as e:
    logger.warning(f"Market router not available: {e}")

# Risk router (Phase 7 - Risk Management API)
try:
    from src.api.routers.risk import router as risk_router
    app.include_router(risk_router)
    logger.info("✓ Mounted Risk Management router (/api/risk)")
except ImportError as e:
    logger.warning(f"Risk router not available: {e}")

# ML router (Phase 7 - ML Model Management API)
try:
    from src.api.routers.ml import router as ml_router
    app.include_router(ml_router)
    logger.info("✓ Mounted ML Model Management router (/api/ml)")
except ImportError as e:
    logger.warning(f"ML router not available: {e}")

# LLM router (Phase 7 - LLM Strategy API)
try:
    from src.api.routers.llm import router as llm_router
    app.include_router(llm_router)
    logger.info("✓ Mounted LLM Strategy router (/api/llm)")
except ImportError as e:
    logger.warning(f"LLM router not available: {e}")

# Autonomous Engine router (Phase 7 - Autonomous Trading)
try:
    from src.api.routers.autonomous_engine import router as autonomous_router
    app.include_router(autonomous_router)
    logger.info("✓ Mounted Autonomous Trading Engine router (/api/autonomous-engine)")
except ImportError as e:
    logger.warning(f"Autonomous engine router not available: {e}")

# Mode Management router (Phase 3.5 - Mode switching)
try:
    from src.api.routers.mode import router as mode_router
    app.include_router(mode_router)
    logger.info("✓ Mounted Mode Management router (/api/mode)")
except ImportError as e:
    logger.warning(f"Mode router not available: {e}")

# Debug & Monitoring router (Observability)
try:
    from src.api.routers.debug import router as debug_router
    app.include_router(debug_router)
    logger.info("✓ Mounted Debug & Monitoring router (/api/debug)")
except ImportError as e:
    logger.warning(f"Debug router not available: {e}")


if __name__ == "__main__":
    # Development server
    # In production, use: uvicorn main:app --host 0.0.0.0 --port 8100 --workers 1
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8100,
        reload=False,  # Disabled to prevent bytecode caching issues
        log_level="info"
    )
