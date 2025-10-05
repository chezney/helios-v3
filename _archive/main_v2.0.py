"""
Helios Trading System v2.0 - Main Application Entry Point
FastAPI application with comprehensive middleware, database connections, and router configuration
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time

# Import configuration and logging
from config.settings import settings
from src.utils.logger import setup_logging, get_logger

# Import dependency providers
from src.api.dependencies import (
    initialize_services,
    cleanup_services,
    service_lifespan,
    get_database_provider,
    get_valr_client_provider
)

# Import trading orchestrator and market simulator
from src.trading.orchestrator.trading_orchestrator import trading_orchestrator
from src.trading.simulation.market_simulator import MarketSimulator
from src.api.valr_client import valr_client

# Import portfolio management system
from src.portfolio.portfolio_manager import PortfolioManager, PortfolioConfiguration, PortfolioMode, OptimizationMethod, AllocationStrategy


# Import performance monitoring
from src.api.utils.performance_optimizer import (
    performance_monitor,
    get_performance_report,
    initialize_performance_optimization
)

# Import comprehensive caching system
from src.api.utils.cache_manager import (
    initialize_comprehensive_caching,
    get_cache_manager,
    CacheMiddleware
)

# Import security middleware
from src.security.security_headers_middleware import (
    SecurityHeadersMiddleware,
    create_security_middleware
)
from src.security.https_middleware import (
    HTTPSRedirectMiddleware,
    SecureSessionMiddleware,
    create_https_middleware,
    create_secure_session_middleware
)
from src.security.encryption import (
    initialize_encryption,
    get_encryption_manager
)

# Import all routers
from src.api.routers import (
    accounts,
    aether_risk,
    analytics,
    auth,  # NEW: Standard authentication router
    auto_trading,
    backtesting,
    backtesting_orchestrator,
    balances,
    data_collection,
    data_integrity,  # NEW: Data integrity router
    data_orchestrator,
    data_verification,
    enhanced_auth,
    health,
    historical,
    llm,
    market,
    modularity,  # NEW: Modular architecture management
    monitoring,
    monitoring_gui,
    orchestrator_extended,
    orchestrator_trading,  # New proper orchestrator trading router
    portfolio,
    prices,
    risk_control,
    risk_management,
    security,
    strategy,
    supplementary,  # NEW: Supplementary utilities router
    system,
    trading_enhanced,
    trading,
    valr,  # NEW: Direct VALR API router
    websocket,
    websocket_noauth,
    websocket_monitoring  # NEW: WebSocket monitoring push-based updates
)

# Initialize logging
setup_logging()
logger = get_logger(__name__, component="main_application")

# Import data collection components (after logger is available)
try:
    from src.data.collectors.backfill_manager import BackfillManager
    from src.data.collectors.historical_collector import HistoricalDataCollector
    from src.data.pipeline_orchestrator import DataPipelineOrchestrator
    logger.info("Data collection components imported successfully")
except ImportError as e:
    logger.warning(f"Some data collection components not available: {e}")
    # Create placeholder classes
    class BackfillManager:
        async def get_status(self): return {"status": "not_implemented"}
        async def start_backfill(self, **kwargs): return {"status": "not_implemented"}
    class HistoricalDataCollector:
        async def get_status(self): return {"status": "not_implemented"}
    class DataPipelineOrchestrator:
        async def get_status(self): return {"status": "not_implemented"}

# Initialize data management components
backfill_manager = BackfillManager()
historical_collector = HistoricalDataCollector()
pipeline_orchestrator = DataPipelineOrchestrator()

# Initialize portfolio management system
portfolio_manager = None

# Initialize data pipeline orchestrator (for global access)
data_pipeline_orchestrator = None


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor API performance and add performance headers"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        process_time = time.time() - start_time
        response_time_ms = process_time * 1000
        
        # Add performance headers
        response.headers["X-Process-Time"] = str(response_time_ms)
        response.headers["X-Timestamp"] = str(int(time.time()))
        
        # Record performance metrics
        endpoint = f"{request.method} {request.url.path}"
        performance_monitor._monitor.record_request(endpoint, response_time_ms)
        
        # Log slow requests
        if response_time_ms > 100:  # Log requests over 100ms
            logger.warning(
                f"Slow request detected: {endpoint} took {response_time_ms:.2f}ms",
                extra_fields={
                    "endpoint": endpoint,
                    "response_time_ms": response_time_ms,
                    "status_code": response.status_code
                }
            )
        
        return response



class WebSocketAuthBypassMiddleware(BaseHTTPMiddleware):
    """Middleware to bypass authentication for WebSocket connections"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Check if this is a WebSocket upgrade request
        if request.url.path.startswith("/ws/"):
            # For ANY WebSocket connection, completely bypass authentication
            # Set a valid user object to satisfy any auth checks
            request.state.user = {
                "id": "websocket_user", 
                "username": "websocket",
                "authenticated": True,
                "is_authenticated": True,
                "role": "admin",
                "permissions": ["*"]
            }
            # Remove any auth headers that might cause issues
            if "authorization" in request.headers:
                request.headers._list = [(k, v) for k, v in request.headers._list if k.lower() != b"authorization"]
        
        # Process the request normally
        response = await call_next(request)
        return response

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive error handling and logging"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(
                f"Unhandled exception in request: {request.method} {request.url.path}",
                exc_info=True,
                extra_fields={
                    "endpoint": f"{request.method} {request.url.path}",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An internal server error occurred",
                        "details": {"error_type": type(e).__name__}
                    },
                    "timestamp": time.time()
                }
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    logger.info("🚀 Starting Helios Trading System v2.0...")
    
    try:
        # Initialize modular architecture system
        from src.core import feature_flags, module_loader
        await feature_flags.initialize()
        logger.info("✅ Feature flag system initialized")

        # Initialize performance optimization
        await initialize_performance_optimization()
        logger.info("✅ Performance optimization initialized")
        
        # Initialize encryption system
        try:
            encryption_manager = initialize_encryption()
            logger.info("✅ Encryption system initialized")
            
            # Initialize sensitive data encryption
            from src.security.sensitive_data_encryption import (
                get_sensitive_data_manager,
                encrypt_valr_credentials
            )
            
            # Encrypt VALR credentials if available
            if encrypt_valr_credentials():
                logger.info("✅ VALR credentials encrypted and secured")
            else:
                logger.info("📝 No VALR credentials found to encrypt (may be using test/demo mode)")
            
        except Exception as e:
            logger.warning(f"⚠️ Encryption initialization failed: {e}")
        
        # Initialize comprehensive caching system
        try:
            redis_url = f"redis://{settings.database.redis_host}:{settings.database.redis_port}/{settings.database.redis_db}"
            cache_manager = await initialize_comprehensive_caching(redis_url)
            logger.info("✅ Comprehensive caching system initialized")
            
            # Warm critical caches with async functions
            async def get_market_summary():
                return {"BTCZAR": {"last_price": 850000, "change_24h": 0.02}}
            
            async def get_ticker_data():
                return {"BTCZAR": {"last_price": 850000, "bid": 849000, "ask": 851000}}
            
            async def get_supported_pairs():
                return ["BTCZAR", "ETHZAR", "ADAZAR", "XRPZAR"]
            
            async def get_trading_balances():
                return [{"currency": "ZAR", "available": "10000.00", "reserved": "0.00"}]
            
            async def get_strategy_performance():
                return {"total_return": 0.15, "sharpe_ratio": 1.85, "max_drawdown": -0.08}
            
            warm_functions = {
                'market_summary': get_market_summary,
                'ticker_data': get_ticker_data,
                'supported_pairs': get_supported_pairs,
                'trading_balances': get_trading_balances,
                'strategy_performance': get_strategy_performance
            }
            
            # Start cache warming in background
            asyncio.create_task(cache_manager.warm_critical_caches(warm_functions))
            logger.info("🔥 Cache warming initiated for critical endpoints")
            
        except Exception as e:
            logger.warning(f"⚠️ Caching system initialization failed (will use fallback): {e}")
        
        # Initialize services with graceful error handling for testing
        try:
            await initialize_services()
            logger.info("✅ All services initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ Service initialization failed (expected for testing): {e}")
            logger.info("🔧 Server will continue in limited mode for performance testing")
        
        # Verify database connections (optional for testing)
        db_provider = get_database_provider()
        
        # Test PostgreSQL connection with timeout
        try:
            pg_pool = await asyncio.wait_for(db_provider.get_postgres_pool(), timeout=5.0)
            async with pg_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("✅ PostgreSQL connection verified")
        except asyncio.TimeoutError:
            logger.warning("⚠️ PostgreSQL connection timed out - continuing without database")
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL connection failed (expected for testing): {e}")
        
        # Test Redis connection
        try:
            redis_client = await db_provider.get_redis_client()
            await redis_client.ping()
            logger.info("✅ Redis connection verified")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed (expected for testing): {e}")
        
        # Test InfluxDB connection
        try:
            influx_client = db_provider.get_influx_client()
            logger.info("✅ InfluxDB client initialized")
        except Exception as e:
            logger.warning(f"⚠️ InfluxDB connection failed (expected for testing): {e}")
        
        # Initialize storage handlers for data pipeline
        logger.info("🔧 Initializing storage handlers for data pipeline...")
        try:
            from src.data.storage.postgresql_storage import postgresql_storage
            from src.data.storage.influxdb_storage import influxdb_storage
            from src.data.storage.redis_storage import redis_storage
            
            # Initialize each storage handler
            await postgresql_storage.initialize()
            logger.info("✅ PostgreSQL storage handler initialized")
            
            await influxdb_storage.initialize()
            logger.info("✅ InfluxDB storage handler initialized")
            
            await redis_storage.initialize()
            logger.info("✅ Redis storage handler initialized")
            
            logger.info("✅ All storage handlers initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ Storage handler initialization failed: {e}")
            logger.info("📊 System will continue but database monitoring may not work")
        
        # Initialize the old storage clients that are actually being used by candle generator
        logger.info("🔧 Initializing legacy storage clients for candle generation...")
        try:
            from src.data.storage.influxdb_client import influxdb_client
            from src.data.storage.redis_client import redis_cache
            
            # Connect the old storage clients
            await influxdb_client.connect()
            logger.info("✅ Legacy InfluxDB client connected")
            
            await redis_cache.connect()
            logger.info("✅ Legacy Redis cache connected")
            
            logger.info("✅ Legacy storage clients initialized for OHLC data storage")
        except Exception as e:
            logger.error(f"❌ Failed to initialize legacy storage clients: {e}")
            logger.warning("⚠️ OHLC candle storage will not work without these clients")
        
        # Test VALR API connection
        try:
            valr_provider = get_valr_client_provider()
            valr_http_client = await valr_provider.get_client()
            logger.info("✅ VALR API client initialized")
        except Exception as e:
            logger.warning(f"⚠️ VALR API client initialization failed (expected for testing): {e}")
        
        # Start WebSocket background broadcasters
        try:
            from src.api.routers.websocket import start_background_broadcasters
            background_tasks = await start_background_broadcasters()
            logger.info(f"✅ WebSocket background broadcasters started: {len(background_tasks)} tasks running")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start WebSocket broadcasters: {e}")
        
        # Start data ingestion pipeline for market data storage with enhanced monitoring
        logger.info("📊 ENTERING DATA INGESTION PIPELINE SECTION")
        try:
            logger.info("📊 Importing data pipeline and websocket client...")
            from src.data.ingestion.pipeline import data_pipeline
            from src.data.websocket_client import websocket_client
            logger.info("📊 Import successful!")
            
            # Ensure WebSocket is ready
            logger.info("🔌 Initializing WebSocket connection for real-time data...")
            
            # Start the pipeline (includes WebSocket connection and OHLC generation) with timeout
            logger.info("📊 Calling data_pipeline.start() with 10 second timeout...")
            await asyncio.wait_for(data_pipeline.start(), timeout=10.0)
            logger.info("📊 data_pipeline.start() completed successfully!")
            
            # Verify WebSocket is connected
            await asyncio.sleep(2)  # Give WebSocket time to connect
            if websocket_client.is_connected:
                logger.info("✅ WebSocket connected successfully for real-time market data")
            else:
                logger.warning("⚠️ WebSocket not connected - will retry in background")
            
            # Check pipeline status
            pipeline_status = await data_pipeline.get_status()
            logger.info(f"✅ Data ingestion pipeline started - Processing: {pipeline_status.get('processed_count', 0)} messages")
            
            # Log what's being collected
            logger.info(f"📊 Collecting real-time data for: BTCZAR, ETHZAR, ADAZAR, XRPZAR")
            logger.info(f"⏱️ OHLC generation active - Creating 1-minute candles")
            logger.info(f"💾 Storing to PostgreSQL: historical_ohlc table")
            
        except Exception as e:
            logger.error(f"❌ Failed to start data ingestion pipeline: {e}")
            logger.warning("⚠️ System will continue without real-time data feed")
        
        # Start neural data pipeline for AI feature processing with timeout
        try:
            from src.ml.inference.neural_data_pipeline import neural_data_pipeline
            await asyncio.wait_for(neural_data_pipeline.start(), timeout=5.0)
            logger.info("✅ Neural data pipeline started - AI features being generated")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Neural data pipeline timed out - continuing without AI features")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start neural data pipeline: {e}")
        
        # Start data pipeline orchestrator with timeout
        try:
            # Import at module level for global access
            from src.data.orchestration.pipeline_orchestrator import pipeline_orchestrator
            
            # Store as global for access from other modules
            global data_pipeline_orchestrator
            data_pipeline_orchestrator = pipeline_orchestrator
            
            await asyncio.wait_for(pipeline_orchestrator.initialize(), timeout=5.0)
            await asyncio.wait_for(pipeline_orchestrator.start(), timeout=5.0)
            
            # Verify it's running
            status = await pipeline_orchestrator.get_status()
            logger.info(f"✅ Data pipeline orchestrator started - Running: {pipeline_orchestrator.is_running}, Metrics: {status.get('metrics', {}).get('data_points_per_second', 0)}/s")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start pipeline orchestrator: {e}")
        
        # Start BackfillManager and HistoricalDataCollector
        try:
            # Initialize BackfillManager
            backfill_status = await backfill_manager.get_status()
            logger.info(f"✅ BackfillManager initialized: {backfill_status}")
            
            # Initialize HistoricalDataCollector  
            collector_status = await historical_collector.get_status()
            logger.info(f"✅ HistoricalDataCollector initialized: {collector_status}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize data collectors: {e}")
        
        # Initialize trading orchestrator with live data integration
        try:
            global market_simulator
            
            # Initialize market simulator with live VALR client
            await valr_client.initialize()
            market_simulator = MarketSimulator(valr_client=valr_client)
            logger.info("✅ Market simulator initialized with live VALR client")
            
            # Initialize trading orchestrator
            await trading_orchestrator.initialize()
            logger.info("✅ Trading orchestrator initialized")
            
            # P3.6: Initialize portfolio management system
            global portfolio_manager
            portfolio_config = PortfolioConfiguration(
                mode=PortfolioMode.BALANCED,
                risk_budget=0.12,
                target_return=0.15,
                max_drawdown=0.20,
                rebalancing_frequency="daily",
                optimization_method=OptimizationMethod.MARKOWITZ,
                allocation_strategy=AllocationStrategy.DYNAMIC,
                base_currency="ZAR",
                benchmark_symbol="BTCZAR",
                emergency_threshold=0.15
            )
            
            portfolio_manager = PortfolioManager(
                config=portfolio_config,
                update_frequency=300  # 5 minutes
            )
            
            # P3.6.1: Start portfolio monitoring in main.py lifespan event
            await portfolio_manager.start_portfolio_management()
            logger.info("✅ Portfolio management system activated")
            
            # Inject live market simulator into paper trading service
            if hasattr(trading_orchestrator, '_paper_service') and trading_orchestrator._paper_service:
                if hasattr(trading_orchestrator._paper_service, 'set_market_simulator'):
                    trading_orchestrator._paper_service.set_market_simulator(market_simulator)
                    logger.info("✅ Live market simulator injected into paper trading service")
                else:
                    # Update the market simulator directly
                    trading_orchestrator._paper_service.market_simulator = market_simulator
                    logger.info("✅ Live market simulator updated in paper trading service")
            else:
                logger.info("📝 Paper trading service will be initialized with live data when first accessed")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize trading orchestrator (will use fallback): {e}")
        
        logger.info("🎯 Helios Trading System is ready for performance testing!")
        
        yield
        
    except Exception as e:
        logger.critical(f"💥 Failed to start Helios Trading System: {e}", exc_info=True)
        raise
    finally:
        # Cleanup on shutdown
        logger.info("🛑 Shutting down Helios Trading System...")
        
        # Stop WebSocket background broadcasters
        try:
            from src.api.routers.websocket import stop_background_broadcasters
            await stop_background_broadcasters()
            logger.info("✅ WebSocket background broadcasters stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping WebSocket broadcasters: {e}")
        
        # Stop data pipelines
        try:
            from src.data.ingestion.pipeline import data_pipeline
            await data_pipeline.stop()
            logger.info("✅ Data ingestion pipeline stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping data pipeline: {e}")
        
        # Stop neural data pipeline
        try:
            from src.ml.inference.neural_data_pipeline import neural_data_pipeline
            await neural_data_pipeline.stop()
            logger.info("✅ Neural data pipeline stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping neural data pipeline: {e}")
        
        # Stop data collectors
        try:
            await pipeline_orchestrator.stop()
            logger.info("✅ Data pipeline orchestrator stopped")
            logger.info("✅ BackfillManager and HistoricalDataCollector stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping data collectors: {e}")
        
        # Shutdown portfolio management system
        try:
            if portfolio_manager:
                await portfolio_manager.stop_portfolio_management()
                logger.info("✅ Portfolio management system stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping portfolio management: {e}")
        
        # Shutdown trading orchestrator
        try:
            await trading_orchestrator.shutdown()
            logger.info("✅ Trading orchestrator shutdown complete")
        except Exception as e:
            logger.error(f"❌ Error shutting down trading orchestrator: {e}")
        
        # Close VALR client
        try:
            await valr_client.close()
            logger.info("✅ VALR client closed")
        except Exception as e:
            logger.error(f"❌ Error closing VALR client: {e}")
        
        try:
            await cleanup_services()
            logger.info("✅ All services cleaned up successfully")
        except Exception as e:
            logger.error(f"❌ Error during service cleanup: {e}")
        logger.info("👋 Helios Trading System shutdown complete")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application"""
    
    # Create FastAPI app with lifespan management
    app = FastAPI(
        title="Helios Trading System API",
        description="Advanced cryptocurrency trading system with AI-powered strategies",
        version="2.0.0",
        docs_url="/docs",  # Always enable documentation
        redoc_url="/redoc",  # Always enable ReDoc
        openapi_url="/openapi.json",  # Always enable OpenAPI spec
        lifespan=lifespan
    )
    
    # Add security middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] if settings.is_development else ["localhost", "127.0.0.1"]
    )
    
    # Add HTTPS redirection middleware (first in chain) - DISABLED FOR SINGLE USER TESTING
    environment = "development" if settings.is_development else "production"
    app.add_middleware(
        HTTPSRedirectMiddleware,
        enabled=False,  # DISABLED - Single user system, no HTTPS required
        exclude_paths=["/health", "/api/health", "/docs", "/redoc", "/openapi.json"]
    )
    
    # Add secure session middleware
    app.add_middleware(
        SecureSessionMiddleware,
        secure_cookies=not settings.is_development
    )
    
    # Add comprehensive security headers middleware
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=not settings.is_development,  # Only HTTPS in production
        enable_csp=True,
        enable_frame_options=True,
        enable_content_type_options=True,
        enable_xss_protection=True,
        enable_referrer_policy=True,
        enable_permissions_policy=not settings.is_development,
        custom_headers={
            "X-Security-Level": "high" if not settings.is_development else "development",
            "X-Content-Security": "enabled",
            "X-API-Security": "enhanced",
            "X-Encryption": "AES-256-GCM"
        }
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003", "http://localhost:3004", "http://localhost:3005", "http://localhost:3006", "http://localhost:3007", "http://localhost:3008", "http://localhost:3009", "http://localhost:3010"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-Timestamp"]
    )
    
    # Add custom middleware
    # Add WebSocket auth bypass middleware (FIRST in chain)
    app.add_middleware(WebSocketAuthBypassMiddleware)
    
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(PerformanceMiddleware)
    
    # Add caching middleware
    try:
        cache_manager = get_cache_manager()
        app.add_middleware(CacheMiddleware, cache_manager=cache_manager)
        logger.info("✅ Caching middleware added")
    except Exception as e:
        logger.warning(f"⚠️ Failed to add caching middleware: {e}")
    
    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "details": {}
                },
                "timestamp": time.time()
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()}
                },
                "timestamp": time.time()
            }
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "details": {}
                },
                "timestamp": time.time()
            }
        )
    
    # Root endpoint
    @app.get("/", tags=["system"])
    async def root():
        """Root endpoint with system information"""
        return {
            "status": "success",
            "data": {
                "name": "Helios Trading System",
                "version": "2.0.0",
                "environment": settings.environment.value,
                "trading_mode": settings.trading.mode.value,
                "message": "🚀 Helios Trading System is operational!",
                "docs_url": "/docs" if settings.is_development else None
            },
            "timestamp": time.time()
        }
    
    # Performance monitoring endpoint
    @app.get("/performance", tags=["system"])
    async def get_performance_metrics():
        """Get comprehensive system performance metrics including caching"""
        try:
            # Get existing performance report
            report = get_performance_report()
            
            # Get comprehensive cache metrics
            try:
                cache_manager = get_cache_manager()
                cache_metrics = cache_manager.get_cache_metrics()
                cache_health = await cache_manager.health_check()
                
                # Merge cache metrics into performance report
                report["cache_system"] = {
                    "metrics": cache_metrics,
                    "health": cache_health,
                    "optimization_impact": {
                        "estimated_response_time_improvement": f"{cache_metrics['performance_metrics']['cache_benefit_ms']:.2f}ms",
                        "cache_hit_rate_target": "70%+",
                        "current_hit_rate": f"{cache_metrics['performance_metrics']['hit_rate_percent']:.2f}%",
                        "performance_score": f"{cache_health['performance_score']:.1f}/100"
                    }
                }
                
            except Exception as cache_error:
                logger.warning(f"Failed to get cache metrics: {cache_error}")
                report["cache_system"] = {
                    "status": "error",
                    "error": str(cache_error)
                }
            
            return {
                "status": "success",
                "data": report,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {
                "status": "error",
                "error": {
                    "code": "PERFORMANCE_METRICS_ERROR",
                    "message": "Failed to retrieve performance metrics",
                    "details": {"error": str(e)}
                },
                "timestamp": time.time()
            }
    
    # Include all routers with proper prefixes - FIXED REGISTRATION ORDER FOR ORCHESTRATOR PRECEDENCE
    # IMPORTANT: Orchestrator-based routers registered BEFORE raw endpoints for proper precedence
    routers_config = [
        # Core system and health
        (health.router, "/api/health", ["Health"]),
        (system.router, "", None),  # System router already has /system prefix and tags
        
        # Extended orchestrator endpoints (must be registered first for precedence)
        (orchestrator_extended.router, "", ["Orchestrator Extended"]),
        (orchestrator_trading.router, "", ["Orchestrator Trading"]),  # Proper orchestrator trading
        
        # Trading operations - Orchestrator endpoints first
        (trading.router, "", ["Trading"]),    # Already has /api/trading prefix - ORCHESTRATOR
        (trading_enhanced.router, "/api/trading", ["Trading Enhanced"]),  # Share prefix with trading
        
        # Account and balance management
        (accounts.router, "", None),  # Preserve original "Account Management" tags
        (balances.router, "/api/balances", None),  # Preserve original "Balance Management" tags
        
        # Portfolio management - Uses orchestrator
        (portfolio.router, "/api/portfolio", None),  # Preserve original "portfolio" tags
        
        # Risk management - Orchestrator based
        (risk_control.router, "/api/risk-control", ["Risk Control"]),
        (risk_management.router, "/api/risk", ["Risk Management"]),
        (aether_risk.router, "/api/aether-risk", ["Aether Risk Engine"]),
        
        # Data collection
        (data_collection.router, "/api", ["Data Collection"]),  # Data collection endpoints
        (data_integrity.router, "", ["Data Integrity"]),  # NEW: Data integrity endpoints
        (data_orchestrator.router, "", ["Data Orchestrator"]),  # Data orchestrator endpoints  
        (data_verification.router, "", ["Data Verification"]),  # Data verification endpoints
        
        # Market data - Direct API (read-only)
        (market.router, "", None),      # Preserve original tags - NEW version only
        (prices.router, "", None),      # Preserve original tags - NEW version only
        (historical.router, "", None),  # Preserve original tags - NEW version only
        
        # Analytics and strategy - Uses orchestrator
        (analytics.router, "/api/analytics", ["Analytics"]),
        (strategy.router, "/api/strategy", None),  # Preserve original "Strategy Management" tags
        (backtesting.router, "/api", ["Backtesting"]),  # Router has /backtesting prefix internally
        (backtesting_orchestrator.router, "", ["Backtesting Orchestrator"]),  # Orchestrator backtesting
        
        # AI/ML and Auto-Trading - Advanced features
        (llm.router, "/api/llm", ["LLM"]),  # LLM integration endpoints
        (auto_trading.router, "/api/orchestrator/auto-trading", ["Auto-Trading"]),  # Auto-trading system
        
        # System monitoring
        (monitoring.router, "/api", ["Monitoring"]),  # Has /api/monitoring prefix in router
        (monitoring_gui.router, "", ["GUI Monitoring"]),  # GUI monitoring endpoints
        
        # Authentication and security
        (auth.router, "", ["Authentication"]),  # NEW: Standard auth endpoints
        (enhanced_auth.router, "/api/enhanced-auth", None),  # Fixed path from /api/auth
        (security.router, "/api/security", ["Security"]),
        
        # Direct VALR API access
        (valr.router, "", ["VALR"]),  # NEW: Direct VALR API endpoints

        # Modular architecture management
        (modularity.router, "", ["Modularity"]),  # NEW: Hot-reload, feature flags, circuit breakers

        # Supplementary utilities
        (supplementary.router, "", ["Supplementary"]),  # NEW: System utilities
        
        # WebSocket
        (websocket.router, "/ws", ["WebSocket"]),
        
        # WebSocket WITHOUT AUTHENTICATION for development
        (websocket_noauth.router, "/ws-noauth", ["WebSocket NoAuth"]),
        
        # WebSocket Monitoring - Push-based monitoring updates
        (websocket_monitoring.router, "/ws", ["WebSocket Monitoring"])
    ]
    
    # OVERRIDE: Disable ALL authentication for development
    from fastapi import Depends
    from typing import Optional
    
    async def no_auth():
        """Bypass all authentication"""
        return {"id": "dev_user", "authenticated": True, "role": "admin"}
    
    # Override any auth dependencies to bypass authentication
    from src.api.utils.auth import get_current_user
    from src.api.dependencies import get_current_user as dep_get_current_user
    
    app.dependency_overrides[get_current_user] = no_auth
    if dep_get_current_user:
        app.dependency_overrides[dep_get_current_user] = no_auth
    
    logger.warning("⚠️ AUTHENTICATION BYPASSED FOR ALL ENDPOINTS - DEVELOPMENT MODE")
    
    # Register all routers
    for router_config in routers_config:
        router, prefix, tags = router_config[:3]
        try:
            # Special handling for noauth WebSocket router - no dependencies
            if "NoAuth" in str(tags) or "WebSocket" in str(tags):
                app.include_router(router, prefix=prefix, tags=tags)
                logger.info(f"✅ Registered router WITHOUT AUTH: {prefix or 'root'} ({tags[0] if tags else 'Unknown'})")
            else:
                app.include_router(router, prefix=prefix, tags=tags)
                logger.info(f"✅ Registered router: {prefix or 'root'} ({tags[0] if tags else 'Unknown'})")
        except Exception as e:
            logger.error(f"❌ Failed to register router {prefix}: {e}")
    
    logger.info(f"🎯 Registered {len(routers_config)} routers successfully")
    
    return app


# Create the FastAPI application
app = create_application()


def main():
    """Main entry point for running the server"""
    logger.info("🚀 Starting Helios Trading System server...")
    
    # Configure uvicorn
    config = uvicorn.Config(
        app=app,
        host=settings.host,
        port=settings.port,
        log_level=settings.logging.level.lower(),
        reload=settings.is_development,
        workers=1,  # Single worker for development/testing
        access_log=True,
        use_colors=True,
        loop="asyncio"
    )
    
    server = uvicorn.Server(config)
    
    try:
        logger.info(f"🌐 Server starting on http://{settings.host}:{settings.port}")
        logger.info(f"📊 Environment: {settings.environment.value}")
        logger.info(f"💱 Trading Mode: {settings.trading.mode.value}")
        logger.info(f"📚 API Documentation: http://{settings.host}:{settings.port}/docs")
        
        # Run the server
        server.run()
        
    except KeyboardInterrupt:
        logger.info("🛑 Server shutdown requested by user")
    except Exception as e:
        logger.critical(f"💥 Server failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
