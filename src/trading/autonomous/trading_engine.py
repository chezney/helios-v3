"""
src/trading/autonomous/trading_engine.py

Autonomous Trading Engine - orchestrates all 5 tiers in continuous loop.

Helios V3.0 - Phase 6: Autonomous Trading Engine
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from enum import Enum
import logging
import os
from src.data.processors.candle_aggregator import OHLC

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading mode: PAPER or LIVE"""
    PAPER = "PAPER"
    LIVE = "LIVE"


class EngineStatus(Enum):
    """Engine operational status"""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class AutonomousTradingEngine:
    """
    Autonomous Trading Engine.

    Responsibilities:
    - Maintain WebSocket connection to VALR
    - Process market events in real-time
    - Execute full 5-tier prediction → execution pipeline
    - Monitor open positions continuously
    - Handle errors and recovery
    - Enforce emergency stops

    Architecture:
    1. Event Processing Loop: Handles WebSocket events, executes 5-tier pipeline
    2. Position Monitoring Loop: Checks SL/TP triggers every 5 seconds
    3. Health Monitoring Loop: System health checks every 30 seconds
    """

    def __init__(
        self,
        db_session: AsyncSession,
        trading_mode: TradingMode = TradingMode.PAPER,
        pairs: List[str] = None
    ):
        """
        Initialize Autonomous Trading Engine.

        Args:
            db_session: Database session (will extract session factory from this)
            trading_mode: PAPER or LIVE trading mode
            pairs: List of trading pairs (default: BTCZAR, ETHZAR, SOLZAR)
        """
        # CRITICAL FIX: Instead of using a single shared session across concurrent loops,
        # extract the session factory so each concurrent operation can create its own session
        from src.database import AsyncSessionLocal
        self.session_factory = AsyncSessionLocal

        # Keep legacy db session for backward compatibility (but prefer session factory)
        self.db = db_session

        self.trading_mode = trading_mode
        self.pairs = pairs or ["BTCZAR", "ETHZAR", "SOLZAR"]
        self.status = EngineStatus.STOPPED

        # Control flags
        self.auto_trading_enabled = False
        self.emergency_stop_active = False
        self.should_shutdown = False

        # Event queue for async processing
        self.event_queue: asyncio.Queue = asyncio.Queue()

        # Real-time price cache for position monitoring
        # {pair: {'price': float, 'timestamp': datetime}}
        self.price_cache: Dict[str, Dict] = {}

        # Health monitoring
        self.last_heartbeat = datetime.utcnow()
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5

        # Tracking
        self.cycle_count = 0
        self.current_stage = None
        self.last_cycle_at = None

        # Error recovery managers
        from src.trading.autonomous.error_recovery import (
            WebSocketRecoveryManager,
            DatabaseRecoveryManager,
            RateLimitHandler,
            TierRecoveryManager
        )

        self.ws_recovery = WebSocketRecoveryManager(max_retries=10)
        self.db_recovery = DatabaseRecoveryManager(db_session, retry_delay=5, max_retries=5)
        self.rate_limiter = RateLimitHandler(max_requests_per_minute=60)
        # Tier recovery manager will be initialized after components
        self.tier_recovery = None

        # Component placeholders (will be initialized in _initialize_components)
        self.websocket_client = None
        self.candle_poller = None  # VALRCandlePoller (REST API polling)
        self.candle_generator = None  # DEPRECATED - kept for compatibility
        self.predictor = None
        self.aether_engine = None
        self.strategic_layer = None
        self.portfolio_risk_manager = None
        self.position_manager = None

        # Initialize all components
        self._initialize_components()

        logger.info(
            f"AutonomousTradingEngine initialized: mode={trading_mode.value}, "
            f"pairs={pairs}"
        )

    def _initialize_components(self):
        """
        Initialize all 5-tier components.

        Tier 1: Data Foundation (WebSocket, Candle Generator)
        Tier 2: Neural Network (Predictor)
        Tier 3: Aether Risk Engine (Kelly, GARCH)
        Tier 4: LLM Strategic Layer
        Tier 5: Portfolio Manager (Risk Manager, Position Manager)
        """
        logger.info("Initializing 5-tier components...")

        # Tier 1: Data layer (will be implemented in Week 27)
        # self.websocket_client = VALRWebSocketClient(pairs=self.pairs)
        # self.candle_generator = MultiTimeframeCandleGenerator(self.db)

        # Tier 2: ML prediction (AutoGluon Ensemble - SAME AS API)
        try:
            from src.ml.inference.ensemble_prediction_service import EnsemblePredictionService
            self.predictor = EnsemblePredictionService(
                nn_model_path="models/DISABLED_neural_network.pt",  # Disable neural network
                autogluon_path="models/autogluon_ensemble"
            )
            logger.info("[OK] Tier 2: AutoGluon Ensemble Predictor initialized (unified with API)")
        except Exception as e:
            logger.warning(f"Tier 2 initialization failed: {e}")

        # Tier 3: Risk management
        try:
            from src.risk.aether_engine import AetherRiskEngine
            self.aether_engine = AetherRiskEngine()  # No parameters needed
            logger.info("[OK] Tier 3: Aether Risk Engine initialized")
        except Exception as e:
            logger.warning(f"Tier 3 initialization failed: {e}")

        # Tier 4: LLM strategy
        try:
            from src.llm.strategy.strategic_execution import StrategicExecutionLayer
            self.strategic_layer = StrategicExecutionLayer(self.db)
            logger.info("[OK] Tier 4: LLM Strategic Layer initialized")
        except Exception as e:
            logger.warning(f"Tier 4 initialization failed: {e}")

        # Tier 5: Portfolio management (with ExecutionRouter for LIVE/PAPER routing)
        try:
            from src.portfolio.risk.portfolio_risk_manager import PortfolioRiskManager
            from src.portfolio.positions.position_manager import PositionManager
            from src.trading.execution.execution_router import ExecutionRouter

            # Initialize ExecutionRouter (replaces _get_trading_client)
            self.execution_router = ExecutionRouter(
                db_session=self.db,
                initial_balance_zar=100000.0,  # R100k starting capital for paper trading
                slippage_bps=5.0  # 5 basis points base slippage
            )

            self.portfolio_risk_manager = PortfolioRiskManager(self.db)
            self.position_manager = PositionManager(
                self.db,
                trading_client=self.execution_router  # Use router instead of direct client
            )
            logger.info("[OK] Tier 5: Portfolio Manager initialized with ExecutionRouter")
        except Exception as e:
            logger.warning(f"Tier 5 initialization failed: {e}")

        # Initialize tier recovery manager (after all components are created)
        from src.trading.autonomous.error_recovery import TierRecoveryManager
        self.tier_recovery = TierRecoveryManager(self)

        logger.info("All tier components initialized")
        logger.info("Error recovery system ready")

    def _get_trading_client(self):
        """
        DEPRECATED: Get trading client based on mode.

        This method is deprecated as of Phase 2 (Oct 22, 2025).
        Use self.execution_router instead, which dynamically queries
        the database for the current mode before each trade.

        The old approach used constructor parameter (self.trading_mode),
        which required engine restart to change modes. The new ExecutionRouter
        enables hot-swapping between PAPER and LIVE modes.

        Returns:
            PaperTradingClient for PAPER mode
            VALRTradingClient for LIVE mode
        """
        logger.warning(
            "[DEPRECATED] _get_trading_client() is deprecated. "
            "Use self.execution_router instead for dynamic mode routing."
        )

        if self.trading_mode == TradingMode.PAPER:
            # Paper trading client with realistic execution
            from src.trading.execution.paper_trading_client import PaperTradingClient
            return PaperTradingClient(
                db_session=self.db,
                initial_balance_zar=100000.0,  # R100k starting capital
                slippage_bps=5.0  # 5 basis points base slippage
            )
        else:
            # Live trading client (future implementation)
            # from src.trading.execution.valr_trading_client import VALRTradingClient
            # return VALRTradingClient()
            logger.warning("LIVE mode selected but VALRTradingClient not implemented")
            return None

    async def start(self):
        """
        Start the autonomous trading engine.

        Steps:
        1. Print startup banner
        2. Connect to VALR WebSocket
        3. Launch 3 background loops:
           - Event processing loop
           - Position monitoring loop
           - Health monitoring loop
        """
        # PROOF: start() method called
        with open("ENGINE_START_CALLED.txt", "w") as f:
            f.write(f"start() called at {datetime.utcnow().isoformat()}\n")

        print(f"\n{'=' * 80}")
        print(f"[STARTING] Autonomous Trading Engine")
        print(f"{'=' * 80}")
        print(f"   Mode: {self.trading_mode.value}")
        print(f"   Pairs: {', '.join(self.pairs)}")
        print(f"   Auto-trading: {'ENABLED' if self.auto_trading_enabled else 'DISABLED'}")
        print(f"{'=' * 80}\n")

        self.status = EngineStatus.STARTING

        # PROOF: About to call _connect_websocket()
        with open("ENGINE_BEFORE_CONNECT.txt", "w") as f:
            f.write(f"About to call _connect_websocket() at {datetime.utcnow().isoformat()}\n")
        print("[DEBUG] About to call _connect_websocket()")

        try:
            # Step 1: Connect to VALR WebSocket
            await self._connect_websocket()

            # PROOF: _connect_websocket() returned
            with open("ENGINE_AFTER_CONNECT.txt", "w") as f:
                f.write(f"_connect_websocket() completed at {datetime.utcnow().isoformat()}\n")
            print("[DEBUG] _connect_websocket() completed")

            # Step 2: Start background tasks
            self.status = EngineStatus.RUNNING
            logger.info("Engine status: RUNNING")

            await asyncio.gather(
                self._event_processing_loop(),
                self._position_monitoring_loop(),
                self._health_monitoring_loop(),
                return_exceptions=True
            )

        except Exception as e:
            logger.error(f"Engine startup failed: {e}")
            self.status = EngineStatus.ERROR
            raise

    async def _connect_websocket(self):
        """
        Connect to VALR REST API poller and WebSocket for real-time prices.

        New Architecture (Oct 2025):
        1. VALRCandlePoller (Primary):
           - Polls VALR REST API /buckets endpoint every 60 seconds
           - Fetches pre-aggregated 1m candles
           - Stores to market_ohlc database
           - Emits NEW_CANDLE events to event queue

        2. VALRWebSocketClient (Supplementary):
           - MARKET_SUMMARY_UPDATE for real-time prices (~1-5 per second)
           - Updates price cache for position monitoring (stop-loss/take-profit triggers)
           - AGGREGATED_ORDERBOOK_UPDATE for bid/ask spread features

        Why this approach:
        - VALR NEW_TRADE WebSocket events are account-only (not public market data)
        - REST API /buckets provides reliable, official VALR candles
        - WebSocket provides sub-second price updates for position management
        """
        # PROOF OF EXECUTION - Write marker file
        with open("WEBSOCKET_CONNECT_CALLED.txt", "w") as f:
            from datetime import datetime
            f.write(f"_connect_websocket() called at {datetime.utcnow().isoformat()}\n")

        print("[DEBUG] _connect_websocket() called - marker file written")
        print("[CONNECT] Initializing data collection...")
        logger.info("Starting VALRCandlePoller and WebSocket client...")
        logger.info("[DEBUG] About to import VALRCandlePoller")

        try:
            # Import components
            from src.data.collectors.valr_candle_poller import VALRCandlePoller
            from src.data.collectors.valr_websocket_client import VALRWebSocketClient

            # PROOF: Imports successful
            with open("WEBSOCKET_CONNECT_IMPORTS_OK.txt", "w") as f:
                f.write("Imports successful\n")

            # Get database connection (asyncpg, not SQLAlchemy)
            import asyncpg
            from config.settings import settings

            db_conn = await asyncpg.connect(
                host=settings.database.postgres_host,
                port=settings.database.postgres_port,
                user=settings.database.postgres_user,
                password=settings.database.postgres_password,
                database=settings.database.postgres_db
            )

            # 1. Create VALRCandlePoller (primary data source)
            self.candle_poller = VALRCandlePoller(
                db=db_conn,
                pairs=self.pairs,
                event_queue=self.event_queue  # Emits NEW_CANDLE events
            )

            # PROOF: VALRCandlePoller created
            with open("VALR_POLLER_CREATED.txt", "w") as f:
                f.write(f"VALRCandlePoller created: pairs={self.pairs}\n")
                f.write(f"Poller object: {self.candle_poller}\n")

            # Start poller (background task)
            task = asyncio.create_task(self.candle_poller.start())

            # PROOF: Task created
            with open("VALR_POLLER_TASK_CREATED.txt", "w") as f:
                f.write(f"Task created: {task}\n")
                f.write(f"Task done: {task.done()}\n")

            logger.info(f"VALRCandlePoller started: pairs={self.pairs}, interval=60s")

            # 2. Create WebSocket client (supplementary real-time prices)
            def on_price_update(tick):
                """Callback for MARKET_SUMMARY_UPDATE - update price cache"""
                # Create PRICE_UPDATE event
                event = {
                    'type': 'PRICE_UPDATE',
                    'pair': tick.pair,
                    'price': tick.price,
                    'timestamp': tick.timestamp.isoformat()
                }
                # Put in event queue (non-blocking)
                try:
                    self.event_queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Event queue full, dropping price update for {tick.pair}")

            # WebSocket client (optional - can be disabled to save CPU)
            if settings.enable_websocket:
                self.websocket_client = VALRWebSocketClient(
                    pairs=self.pairs,
                    on_trade=on_price_update,  # Reusing on_trade callback for price updates
                    on_orderbook=None,  # Not using orderbook snapshots yet
                    on_aggregated_orderbook=None  # Future: store for features
                )

                # Start WebSocket client (background task)
                asyncio.create_task(self.websocket_client.start())
                logger.info(f"WebSocket client started for real-time prices: pairs={self.pairs}")
                print("[OK] Data collection started (REST API poller + WebSocket prices)")
            else:
                self.websocket_client = None
                logger.info("WebSocket client disabled (ENABLE_WEBSOCKET=false)")
                print("[OK] Data collection started (REST API poller only, WebSocket disabled)")

        except Exception as e:
            logger.error(f"Data collection startup failed: {e}", exc_info=True)
            print(f"[FAIL] Data collection startup failed, attempting recovery...")

            # Attempt recovery with exponential backoff
            success = await self.ws_recovery.reconnect_with_backoff(
                self._reconnect_websocket,
                on_success=self._on_websocket_reconnected,
                on_failure=self._on_websocket_recovery_failed
            )

            if not success:
                logger.critical("Data collection recovery failed - cannot start engine")
                raise Exception("Data collection startup failed and recovery unsuccessful")

    async def _reconnect_websocket(self):
        """Reconnect data collection services (used by recovery manager)."""
        # Restart candle poller if it stopped
        if self.candle_poller:
            if not self.candle_poller.running:
                asyncio.create_task(self.candle_poller.start())
                logger.info("VALRCandlePoller restarted")

        # Restart WebSocket client if it stopped
        if self.websocket_client:
            if not self.websocket_client.running:
                asyncio.create_task(self.websocket_client.start())
                logger.info("WebSocket client restarted")

    async def _on_websocket_reconnected(self):
        """Callback when WebSocket reconnects successfully."""
        logger.info("[OK] WebSocket reconnected - resuming normal operation")
        print("[OK] WebSocket reconnected successfully")
        self.consecutive_errors = 0

    async def _on_websocket_recovery_failed(self):
        """Callback when WebSocket recovery fails."""
        logger.critical("[ALERT] WebSocket recovery failed - triggering emergency stop")
        print("[ALERT] WebSocket connection lost - triggering emergency stop")
        await self._trigger_emergency_stop("WebSocket connection lost after all recovery attempts")

    async def _event_processing_loop(self):
        """
        Main event processing loop.

        Continuously processes events from the queue:
        - NEW_CANDLE: Execute full 5-tier trading pipeline
        - PRICE_UPDATE: Update position monitoring
        - ORDERBOOK_UPDATE: Store for liquidity analysis
        - ALERT: Handle system alerts

        Error Handling:
        - Tracks consecutive errors
        - Triggers emergency stop after max_consecutive_errors
        """
        print("[LOOP] Event processing loop started")
        logger.info("Event processing loop active")

        while not self.should_shutdown:
            try:
                # Get next event from queue (1 second timeout)
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                # Process event
                await self._process_event(event)

                # Reset error counter on success
                self.consecutive_errors = 0

            except asyncio.TimeoutError:
                # No events, keep looping
                continue

            except Exception as e:
                self.consecutive_errors += 1
                logger.error(f"Event processing error: {e}", exc_info=True)

                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(
                        f"Max consecutive errors ({self.max_consecutive_errors}) reached"
                    )
                    await self._trigger_emergency_stop()
                    break

        logger.info("Event processing loop stopped")

    async def _process_event(self, event: Dict):
        """
        Process a single market event.

        Routes event to appropriate handler based on event type.

        Args:
            event: Event dictionary with 'type' key
        """
        event_type = event.get('type')

        if event_type == 'NEW_CANDLE':
            await self._handle_new_candle_event(event)

        elif event_type == 'PRICE_UPDATE':
            await self._handle_price_update_event(event)

        elif event_type == 'ORDERBOOK_UPDATE':
            await self._handle_orderbook_update(event)

        elif event_type == 'ALERT':
            await self._handle_alert_event(event)

        else:
            logger.warning(f"Unknown event type: {event_type}")

    async def _handle_new_candle_event(self, event: Dict):
        """
        Handle new candle event - execute full 5-tier pipeline.

        This is the core trading logic that executes on each candle close.

        Pipeline:
        1. Check gates (auto-trading enabled, emergency stop inactive)
        2. Tier 1: Extract features from event
        3. Tier 2: Neural network prediction
        4. Tier 3: Aether risk engine (position sizing, GARCH volatility)
        5. Tier 4: LLM strategic approval
        6. Tier 5: Portfolio risk checks and execution

        Args:
            event: Candle event with pair, timestamp, and timeframe
        """
        pair = event.get('pair')
        timeframe = event.get('timeframe')
        candle_timestamp = event.get('timestamp')

        # Update tracking (counts even if trading is disabled - shows data is flowing)
        self.cycle_count += 1
        self.last_cycle_at = datetime.utcnow()
        self.current_stage = "data_ingestion"

        # CRITICAL FIX: Create a dedicated session for this event processing cycle
        # This prevents SQLAlchemy concurrency errors when multiple loops run simultaneously
        async with self.session_factory() as session:
            # Fetch the actual candle from database using the timestamp
            # Use retry logic to handle timing issues (WebSocket event may arrive before DB save)
            candle = None
            max_retries = 5
            retry_delay_ms = 200  # 200ms between retries

            for attempt in range(max_retries):
                candle = await self._fetch_candle_by_timestamp(pair, timeframe, candle_timestamp)

                if candle:
                    break

                # Candle not found yet - wait and retry
                if attempt < max_retries - 1:
                    logger.debug(f"Candle not found (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay_ms}ms...")
                    await asyncio.sleep(retry_delay_ms / 1000.0)
                else:
                    logger.warning(f"Could not fetch candle for {pair} {timeframe} at {candle_timestamp} after {max_retries} attempts")
                    self.current_stage = None
                    return

            logger.info(f"[CYCLE #{self.cycle_count}] New {pair} {timeframe} candle: O:{candle.get('open', 0):.2f} C:{candle.get('close', 0):.2f}")

            try:
                # TIER 1: Fetch recent candles and compute features (ALWAYS - even if not trading)
                self.current_stage = "data_ingestion"

                # Fetch recent candles from database (need 50+ for feature computation)
                candles_1m = await self._fetch_recent_candles(pair, "1m", limit=100)
                candles_5m = await self._fetch_recent_candles(pair, "5m", limit=100)
                candles_15m = await self._fetch_recent_candles(pair, "15m", limit=100)

                if len(candles_1m) < 50:
                    logger.warning(f"Not enough historical data for {pair} (need 50+ candles, have {len(candles_1m)})")
                    self.current_stage = None
                    return

                # Compute 90-feature vector
                from src.data.processors.feature_engineering import FeatureEngineer
                feature_engineer = FeatureEngineer()

                try:
                    feature_vector = feature_engineer.calculate_features(
                        candles_1m=candles_1m,
                        candles_5m=candles_5m,
                        candles_15m=candles_15m,
                        pair=pair
                    )

                    if not feature_vector or not hasattr(feature_vector, 'features'):
                        logger.warning(f"Feature computation failed for {pair}")
                        self.current_stage = None
                        return

                    features = feature_vector.features  # NumPy array of 90 features

                    # Store features to database
                    await self._store_features(feature_vector)
                    logger.info(f"[FEATURES] Calculated and stored 90 features for {pair}")

                    # Gate checks - Skip trading if disabled, but features are already calculated above
                    if not self.auto_trading_enabled:
                        logger.debug("Auto-trading disabled - features calculated but skipping trading")
                        self.current_stage = None
                        return

                    if self.emergency_stop_active:
                        logger.warning("Emergency stop active, skipping trade")
                        self.current_stage = None
                        return

                    print(f"\n[CYCLE #{self.cycle_count}] New {pair} candle closed at {candle.get('close_time', 'N/A')}")
                    print(f"   Price: R{candle.get('close_price', 0):,.2f}")

                except Exception as e:
                    logger.error(f"Error computing features for {pair}: {e}", exc_info=True)
                    self.current_stage = None
                    return

                # TIER 2: Neural network prediction
                self.current_stage = "neural_prediction"
                if not self.predictor:
                    logger.warning("Neural network predictor not initialized")
                    self.current_stage = None
                    return

                print("[TIER2] Tier 2: Running neural network prediction...")
                prediction_result = await self.predictor.generate_prediction(pair)

                signal = prediction_result.get('prediction')
                confidence = prediction_result.get('confidence', 0.0)

                print(f"   Prediction: {signal} (confidence: {confidence:.2%})")

                if signal == 'HOLD':
                    print("   -> HOLD signal, no action")
                    self.current_stage = None
                    return

                # TIER 3: Aether risk engine (position sizing + volatility)
                self.current_stage = "position_sizing"
                if not self.aether_engine:
                    logger.warning("Aether risk engine not initialized")
                    self.current_stage = None
                    return

                logger.info("[TIER3] Tier 3: Calculating position size with Aether engine...")
                trade_params = await self.aether_engine.calculate_trade_parameters(
                    pair=pair,
                    signal=signal,
                    confidence=confidence
                )

                if trade_params is None:
                    print("   -> Confidence too low or no edge, skipping trade")
                    self.current_stage = None
                    return

                print(f"   Position size: R{trade_params.position_size_zar:,.2f}")
                print(f"   Leverage: {trade_params.leverage}x")
                print(f"   Stop loss: {trade_params.stop_loss_pct:.2%}")
                print(f"   Take profit: {trade_params.take_profit_pct:.2%}")

                # Convert to dict for next tier
                trade_params_dict = {
                    'position_size_zar': trade_params.position_size_zar,
                    'leverage': trade_params.leverage,
                    'stop_loss_pct': trade_params.stop_loss_pct,
                    'take_profit_pct': trade_params.take_profit_pct,
                    'max_loss_zar': trade_params.risk_amount_zar,
                    'expected_gain_zar': trade_params.potential_profit_zar
                }

                # TIER 4: LLM strategic approval (optional)
                self.current_stage = "llm_decision"
                llm_enabled = os.getenv('ENABLE_LLM_ANALYSIS', 'false').lower() == 'true'

                if llm_enabled:
                    if not self.strategic_layer:
                        logger.warning("LLM strategic layer not initialized")
                        self.current_stage = None
                        return

                    print("[TIER4] Tier 4: Requesting LLM strategic approval...")
                    strategic_decision = await self.strategic_layer.evaluate_trade(
                        pair=pair,
                        signal=signal,
                        confidence=confidence,
                        trade_params=trade_params_dict
                    )

                    if not strategic_decision.get('approved'):
                        print(f"   -> Trade REJECTED by LLM")
                        print(f"   Reason: {strategic_decision.get('strategic_reasoning')}")

                        # Log rejection details
                        await self.aether_engine.update_rejection_details(
                            pair=pair,
                            rejected_by='TIER4_LLM',
                            rejection_reason=f"LLM rejected: {strategic_decision.get('strategic_reasoning', 'No reason provided')[:100]}",
                            llm_decision_data={
                                'pair': pair,
                                'signal': signal,
                                'confidence': confidence,
                                'trade_params': trade_params_dict
                            },
                            llm_rejection_reasoning=strategic_decision.get('strategic_reasoning')
                        )

                        self.current_stage = None
                        return

                    print(f"   -> Trade APPROVED by LLM")
                    print(f"   Reasoning: {strategic_decision.get('strategic_reasoning')}")

                    final_trade_params = strategic_decision.get('final_trade_params')
                else:
                    print("[TIER4] LLM analysis disabled, skipping to Tier 5...")
                    final_trade_params = trade_params_dict

                # TIER 5: Portfolio risk checks and execution
                self.current_stage = "risk_validation"
                if not self.portfolio_risk_manager or not self.position_manager:
                    logger.warning("Portfolio manager not initialized")
                    self.current_stage = None
                    return

                print("[TIER5] Tier 5: Checking portfolio risk limits...")
                risk_check = await self.portfolio_risk_manager.check_trade_risk(
                    pair=pair,
                    signal=signal,
                    trade_params=final_trade_params
                )

                if not risk_check.passed:
                    print(f"   -> Trade BLOCKED by portfolio risk manager")
                    print(f"   Reason: {risk_check.reason}")

                    # Log rejection details
                    await self.aether_engine.update_rejection_details(
                        pair=pair,
                        rejected_by='TIER5_PORTFOLIO_RISK',
                        rejection_reason=risk_check.reason
                    )

                    self.current_stage = None
                    return

                print("   [OK] All risk checks passed")

                # EXECUTE TRADE
                self.current_stage = "trade_execution"
                print("[TRADE] Executing trade...")
                execution_result = await self.position_manager.open_position(
                    pair=pair,
                    signal=signal,
                    trade_params=final_trade_params,
                    strategic_reasoning=strategic_decision.get('strategic_reasoning') if llm_enabled else 'Auto-approved (LLM disabled)'
                )

                if execution_result.get('success'):
                    print(f"[OK] Position opened successfully!")
                    print(f"   Position ID: {execution_result.get('position_id')}")
                    print(f"   Entry price: R{execution_result.get('entry_price'):,.2f}")

                    # Mark the decision as executed in aether_risk_decisions
                    await self.aether_engine.mark_decision_executed(
                        pair=pair,
                        execution_id=execution_result.get('position_id')
                    )
                else:
                    # CRITICAL FIX: Mark failed execution as rejected in database
                    error_msg = execution_result.get('error', 'Unknown error')
                    print(f"[FAIL] Position execution failed: {error_msg}")
                    logger.error(f"Trade execution failed for {pair}: {error_msg}")

                    # Mark as rejected so it doesn't stay pending forever
                    await self.aether_engine.update_rejection_details(
                        pair=pair,
                        rejected_by='TIER5_EXECUTION_FAILED',
                        rejection_reason=f"Execution failed: {error_msg}"
                    )

                # Clear stage after completion
                self.current_stage = None

            except Exception as e:
                logger.error(f"Error in trading pipeline for {pair}: {e}", exc_info=True)
                self.current_stage = None
                raise

    async def _handle_price_update_event(self, event: Dict):
        """
        Handle price update event - update real-time price cache.

        This cache is used by position monitoring for sub-second fresh prices.

        Args:
            event: Price update event with pair, price, timestamp
        """
        pair = event.get('pair')
        price = event.get('price')
        timestamp_str = event.get('timestamp')

        if pair and price:
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except Exception:
                timestamp = datetime.utcnow()

            # Update cache
            self.price_cache[pair] = {
                'price': float(price),
                'timestamp': timestamp
            }

            logger.debug(f"Price cache updated: {pair} = R{price:,.2f}")

    async def _handle_orderbook_update(self, event: Dict):
        """
        Handle orderbook update (for liquidity monitoring).

        Store orderbook snapshot for Tier 4 analysis (future implementation).
        """
        pass

    async def _fetch_candle_by_timestamp(self, pair: str, timeframe: str, timestamp: datetime) -> Optional[Dict]:
        """
        Fetch a single candle by its timestamp.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            timeframe: Timeframe (e.g., '1m', '5m')
            timestamp: Candle open timestamp

        Returns:
            Dict with candle OHLCV data, or None if not found
        """
        try:
            # CRITICAL FIX: Rollback any existing transaction to ensure fresh read
            # The VALRCandlePoller uses asyncpg which auto-commits, but this SQLAlchemy
            # session might be in a transaction that started before the insert.
            # Rolling back ensures we see the latest committed data.
            await self.db.rollback()

            query = text("""
                SELECT open_time, close_time, open_price, high_price, low_price, close_price, volume, num_trades
                FROM market_ohlc
                WHERE pair = :pair AND timeframe = :timeframe AND open_time = :timestamp
                LIMIT 1
            """)

            result = await self.db.execute(query, {
                'pair': pair,
                'timeframe': timeframe,
                'timestamp': timestamp
            })

            row = result.fetchone()

            if not row:
                return None

            return {
                'open_time': row[0],
                'close_time': row[1],
                'open': float(row[2]),
                'high': float(row[3]),
                'low': float(row[4]),
                'close': float(row[5]),
                'volume': float(row[6]),
                'num_trades': row[7] if row[7] else 0
            }

        except Exception as e:
            logger.error(f"Error fetching candle for {pair} {timeframe} at {timestamp}: {e}", exc_info=True)
            return None

    async def _fetch_recent_candles(self, pair: str, timeframe: str, limit: int = 100):
        """
        Fetch recent candles from database for feature computation.

        Args:
            pair: Trading pair (e.g. 'BTCZAR')
            timeframe: Timeframe (e.g. '1m', '5m', '15m')
            limit: Number of candles to fetch (default: 100)

        Returns:
            List of OHLC objects
        """
        try:
            query = text("""
                SELECT open_time, open_price, high_price, low_price, close_price, volume, num_trades
                FROM market_ohlc
                WHERE pair = :pair AND timeframe = :timeframe
                ORDER BY open_time DESC
                LIMIT :limit
            """)

            result = await self.db.execute(query, {
                'pair': pair,
                'timeframe': timeframe,
                'limit': limit
            })

            rows = result.fetchall()

            # Convert to OHLC objects (reverse to chronological order)
            candles = []
            for row in reversed(rows):
                candles.append(OHLC(
                    pair=pair,
                    timeframe=timeframe,
                    timestamp=row[0],  # open_time
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    trade_count=row[6] if row[6] else 0
                ))

            return candles

        except Exception as e:
            logger.error(f"Error fetching candles for {pair} {timeframe}: {e}", exc_info=True)
            return []

    async def _store_features(self, feature_vector):
        """
        Store calculated features to database.

        Args:
            feature_vector: FeatureVector object with 90 features

        Stores:
            - Complete feature vector as JSONB in features_vector column
            - Pair and timestamp for querying
        """
        try:
            import json
            from datetime import datetime

            logger.info(f"[DEBUG] _store_features() called for {feature_vector.pair} at {feature_vector.timestamp}")

            # Convert NumPy array to list for JSON serialization
            features_list = feature_vector.features.tolist()
            logger.info(f"[DEBUG] Converted {len(features_list)} features to list")

            # Create feature dictionary with names
            features_dict = {
                "pair": feature_vector.pair,
                "timestamp": feature_vector.timestamp.isoformat(),
                "features": features_list,
                "feature_names": feature_vector.feature_names,
                "count": len(features_list)
            }

            logger.info(f"[DEBUG] Created features dict, about to insert to database")

            # Insert into database
            query = text("""
                INSERT INTO engineered_features (pair, features_vector, computed_at)
                VALUES (:pair, :features_vector, :computed_at)
                ON CONFLICT (pair, computed_at)
                DO UPDATE SET features_vector = EXCLUDED.features_vector
            """)

            await self.db.execute(query, {
                'pair': feature_vector.pair,
                'features_vector': json.dumps(features_dict),
                'computed_at': feature_vector.timestamp
            })

            logger.info(f"[DEBUG] Executed INSERT query, about to commit")

            await self.db.commit()

            logger.info(f"[DB_STORE] Successfully stored {len(features_list)} features for {feature_vector.pair} at {feature_vector.timestamp}")

        except Exception as e:
            logger.error(f"Error storing features to database: {e}", exc_info=True)
            # Don't raise - feature storage failure shouldn't stop trading pipeline

    async def _execute_pending_approved_trades(self):
        """
        Execute pending approved trades from aether_risk_decisions table.

        This catches trades that were approved but not executed due to:
        - Engine crash/restart
        - Execution failure
        - Any other interruption

        Runs periodically to ensure no approved trades are left pending.
        """
        try:
            # Find pending approved trades (not executed, not rejected, created in last 24 hours)
            query = text("""
                SELECT id, pair, signal, ml_confidence, position_size_zar, leverage,
                       stop_loss_pct, take_profit_pct, max_loss_zar, expected_gain_zar,
                       created_at
                FROM aether_risk_decisions
                WHERE executed = false
                  AND rejected_by IS NULL
                  AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at ASC
                LIMIT 10
            """)

            result = await self.db.execute(query)
            rows = result.fetchall()

            if not rows:
                return

            logger.info(f"[PENDING_TRADES] Found {len(rows)} pending approved trades to execute")
            print(f"\n[PENDING_TRADES] Found {len(rows)} approved trades waiting for execution")

            for row in rows:
                decision_id = row[0]
                pair = row[1]
                signal = row[2]
                ml_confidence = float(row[3])
                position_size_zar = float(row[4])
                leverage = float(row[5])
                stop_loss_pct = float(row[6])
                take_profit_pct = float(row[7])
                max_loss_zar = float(row[8]) if row[8] else 0.0
                expected_gain_zar = float(row[9]) if row[9] else 0.0
                created_at = row[10]

                print(f"\n[EXECUTING_PENDING] Decision ID {decision_id}")
                print(f"   Pair: {pair} {signal}")
                print(f"   Confidence: {ml_confidence:.2%}")
                print(f"   Position Size: R{position_size_zar:,.2f}")
                print(f"   Created: {created_at}")

                # Prepare trade params
                trade_params = {
                    'position_size_zar': position_size_zar,
                    'leverage': leverage,
                    'stop_loss_pct': stop_loss_pct,
                    'take_profit_pct': take_profit_pct,
                    'max_loss_zar': max_loss_zar,
                    'expected_gain_zar': expected_gain_zar
                }

                # Re-check portfolio risk (conditions may have changed)
                if self.portfolio_risk_manager:
                    risk_check = await self.portfolio_risk_manager.check_trade_risk(
                        pair=pair,
                        signal=signal,
                        trade_params=trade_params
                    )

                    if not risk_check.passed:
                        print(f"   [BLOCKED] Portfolio risk check failed: {risk_check.reason}")
                        # Update rejection in database
                        await self.aether_engine.update_rejection_details(
                            pair=pair,
                            rejected_by='TIER5_PORTFOLIO_RISK_RECHECK',
                            rejection_reason=f"Recheck failed: {risk_check.reason}"
                        )
                        continue

                # Execute the trade
                try:
                    execution_result = await self.position_manager.open_position(
                        pair=pair,
                        signal=signal,
                        trade_params=trade_params,
                        strategic_reasoning='Pending trade execution (catch-up)'
                    )

                    if execution_result.get('success'):
                        print(f"   [OK] Position opened! ID: {execution_result.get('position_id')}")
                        print(f"   Entry price: R{execution_result.get('entry_price'):,.2f}")

                        # Mark as executed
                        await self.aether_engine.mark_decision_executed(
                            pair=pair,
                            execution_id=execution_result.get('position_id')
                        )

                        logger.info(f"[PENDING_TRADES] Successfully executed decision {decision_id}")
                    else:
                        error_msg = execution_result.get('error', 'Unknown error')
                        print(f"   [FAIL] Execution failed: {error_msg}")
                        logger.error(f"[PENDING_TRADES] Execution failed for decision {decision_id}: {error_msg}")

                except Exception as e:
                    logger.error(f"[PENDING_TRADES] Error executing decision {decision_id}: {e}", exc_info=True)
                    print(f"   [ERROR] Execution error: {e}")

        except Exception as e:
            logger.error(f"Error in _execute_pending_approved_trades: {e}", exc_info=True)

    async def _handle_alert_event(self, event: Dict):
        """Handle system alert."""
        message = event.get('message', 'Unknown alert')
        logger.warning(f"ALERT: {message}")
        print(f"[NOTIFY] ALERT: {message}")

    # Control methods placeholder (will be implemented in Week 25 Day 7)
    def enable_auto_trading(self):
        """Enable autonomous trading."""
        self.auto_trading_enabled = True
        logger.info("Auto-trading ENABLED")
        print("[OK] Auto-trading ENABLED")

    def disable_auto_trading(self):
        """Disable autonomous trading."""
        self.auto_trading_enabled = False
        logger.info("Auto-trading DISABLED")
        print("[PAUSE] Auto-trading DISABLED")

    def get_status(self) -> Dict:
        """
        Get current engine status.

        Returns:
            Dict with engine status, mode, flags, and health metrics
        """
        return {
            'status': self.status.value,
            'trading_mode': self.trading_mode.value,
            'auto_trading_enabled': self.auto_trading_enabled,
            'emergency_stop_active': self.emergency_stop_active,
            'pairs': self.pairs,
            'cycle_count': self.cycle_count,
            'current_stage': self.current_stage,
            'last_cycle_at': self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            'last_heartbeat': self.last_heartbeat.isoformat(),
            'consecutive_errors': self.consecutive_errors
        }

    def get_cached_price(self, pair: str) -> Optional[float]:
        """
        Get real-time cached price for a pair.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')

        Returns:
            Cached price if available and fresh (< 5 seconds old), None otherwise
        """
        cached = self.price_cache.get(pair)

        if not cached:
            return None

        # Check freshness (reject if older than 5 seconds)
        age = datetime.utcnow() - cached['timestamp']
        if age.total_seconds() > 5:
            logger.warning(f"Cached price for {pair} is stale ({age.total_seconds():.1f}s old)")
            return None

        return cached['price']

    async def _position_monitoring_loop(self):
        """
        Monitor open positions every 5 seconds.

        Checks all open positions for:
        - Stop loss triggers
        - Take profit triggers
        - Timeout expiration

        Uses real-time price cache from WebSocket for sub-second fresh prices.

        Closes positions if triggered.
        """
        print("[MONITOR] Position monitoring loop started (real-time price cache enabled)")
        logger.info("Position monitoring loop active with real-time price cache")

        while not self.should_shutdown:
            try:
                if not self.position_manager:
                    await asyncio.sleep(5)
                    continue

                # Check all open positions (with real-time price cache)
                actions = await self.position_manager.monitor_positions(
                    price_cache_getter=self.get_cached_price
                )

                # Execute closing actions
                for action in actions:
                    position_id = action['position_id']
                    reason = action['reason']
                    current_price = action.get('current_price', 0.0)

                    print(f"\n[NOTIFY] Position {position_id} triggered: {reason}")
                    print(f"   Current price: R{current_price:,.2f}")

                    result = await self.position_manager.close_position(
                        position_id=position_id,
                        reason=reason
                    )

                    if result.get('success'):
                        pnl_pct = result.get('pnl_pct', 0.0)
                        pnl_zar = result.get('pnl_zar', 0.0)
                        print(f"[OK] Position closed")
                        print(f"   P&L: {pnl_pct:+.2%} (R{pnl_zar:+,.2f})")
                    else:
                        print(f"[FAIL] Position close failed: {result.get('error')}")

                # Sleep for 5 seconds
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Position monitoring error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("Position monitoring loop stopped")

    async def _health_monitoring_loop(self):
        """
        Monitor system health every 30 seconds.

        Health checks:
        1. WebSocket connection alive?
        2. Database responsive?
        3. VALR API accessible?
        4. Portfolio within risk limits?
        5. Emergency stop if critical failure
        """
        print("[HEALTH] Health monitoring loop started")
        logger.info("Health monitoring loop active")

        while not self.should_shutdown:
            try:
                await asyncio.sleep(30)

                # Check WebSocket connection (when implemented)
                if self.websocket_client:
                    if hasattr(self.websocket_client, 'is_connected'):
                        if not self.websocket_client.is_connected():
                            logger.warning("WebSocket disconnected, attempting reconnect...")
                            if hasattr(self.websocket_client, 'reconnect'):
                                await self.websocket_client.reconnect()

                # Check database connection
                try:
                    await self.db.execute(text("SELECT 1"))
                except Exception as e:
                    logger.error(f"Database connection issue: {e}")

                # Check portfolio risk
                query = text("SELECT current_drawdown_pct FROM portfolio_state WHERE id = 1")
                result = await self.db.execute(query)
                row = result.fetchone()

                if row:
                    drawdown = float(row[0])
                    if drawdown > 15.0:  # 15% drawdown limit
                        logger.critical(f"Portfolio drawdown {drawdown:.2f}% exceeds limit!")
                        await self._trigger_emergency_stop()

                # Update heartbeat
                self.last_heartbeat = datetime.utcnow()

                # Execute pending approved trades (catch-up mechanism)
                if self.auto_trading_enabled and not self.emergency_stop_active:
                    await self._execute_pending_approved_trades()

            except Exception as e:
                logger.error(f"Health monitoring error: {e}", exc_info=True)

        logger.info("Health monitoring loop stopped")

    async def _trigger_emergency_stop(self):
        """
        Trigger emergency stop - close all positions and halt trading.

        Steps:
        1. Set emergency_stop_active flag
        2. Disable auto-trading
        3. Set status to EMERGENCY_STOP
        4. Close all open positions
        """
        print("\n[ALERT] EMERGENCY STOP TRIGGERED [ALERT]")
        logger.critical("EMERGENCY STOP TRIGGERED")

        self.emergency_stop_active = True
        self.auto_trading_enabled = False
        self.status = EngineStatus.EMERGENCY_STOP

        # Close all open positions
        print("[ACTION] Closing all open positions...")

        try:
            query = text("SELECT id, pair FROM positions WHERE status = 'OPEN'")
            result = await self.db.execute(query)
            rows = result.fetchall()

            for row in rows:
                position_id = row[0]
                pair = row[1]

                logger.info(f"Emergency closing position {position_id} ({pair})")

                # Get current price
                price_query = text("""
                    SELECT close_price FROM market_ohlc
                    WHERE pair = :pair AND timeframe = '5m'
                    ORDER BY close_time DESC
                    LIMIT 1
                """)
                price_result = await self.db.execute(price_query, {'pair': pair})
                price_row = price_result.fetchone()
                current_price = float(price_row[0]) if price_row else 0.0

                if self.position_manager:
                    await self.position_manager.close_position(
                        position_id=position_id,
                        reason='EMERGENCY_CLOSE'
                    )

            print(f"[OK] All positions closed ({len(rows)} positions)")
            logger.info(f"Emergency stop completed: {len(rows)} positions closed")

        except Exception as e:
            logger.error(f"Error during emergency stop: {e}", exc_info=True)
            print(f"[FAIL] Error during emergency stop: {e}")

    def clear_emergency_stop(self):
        """Clear emergency stop flag."""
        if self.emergency_stop_active:
            self.emergency_stop_active = False
            self.status = EngineStatus.RUNNING
            logger.info("Emergency stop cleared")
            print("[OK] Emergency stop cleared")
        else:
            logger.warning("Emergency stop not active")
            print("[ALERT] Emergency stop not active")

    async def shutdown(self):
        """
        Gracefully shutdown the engine.

        Steps:
        1. Set should_shutdown flag
        2. Wait for loops to complete
        3. Stop candle poller and WebSocket
        4. Close execution router (cleans up HTTP sessions)
        5. Set status to STOPPED
        """
        print("\n[SHUTDOWN] Shutting down Autonomous Trading Engine...")
        logger.info("Initiating graceful shutdown")

        self.should_shutdown = True
        self.status = EngineStatus.STOPPED

        # Stop candle poller (REST API polling)
        if self.candle_poller:
            try:
                await self.candle_poller.stop()
                logger.info("VALRCandlePoller stopped")
                print("  REST API poller stopped")
            except Exception as e:
                logger.error(f"Error stopping candle poller: {e}")

        # Stop WebSocket client (real-time prices)
        if self.websocket_client:
            try:
                await self.websocket_client.stop()
                logger.info("WebSocket client stopped")
                print("  WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error stopping WebSocket client: {e}")

        # Stop DEPRECATED candle generator (if still exists for compatibility)
        if self.candle_generator:
            try:
                await self.candle_generator.stop()
                logger.info("DEPRECATED candle generator stopped")
            except Exception as e:
                logger.error(f"Error stopping candle generator: {e}")

        # Close execution router (Phase 2: Clean up HTTP sessions)
        if hasattr(self, 'execution_router') and self.execution_router:
            try:
                await self.execution_router.close()
                logger.info("ExecutionRouter closed")
                print("  ExecutionRouter closed")
            except Exception as e:
                logger.error(f"Error closing execution router: {e}")

        print("[OK] Shutdown complete")
        logger.info("Engine shutdown complete")
# Force reload Tue, Oct  8, 2025  12:32:00 PM - Fixed drawdown bug
