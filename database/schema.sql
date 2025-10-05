-- ============================================================
-- Helios Trading System V3.0 - Complete Database Schema
-- PostgreSQL Database Schema (Following PRD specification)
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ============================================================
-- TIER 1: DATA INGESTION & FEATURE ENGINEERING
-- ============================================================

-- Raw market data from VALR WebSocket (OHLC candles)
CREATE TABLE market_ohlc (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,  -- '1m', '5m', '15m', '1h', '1d'
    open_price DECIMAL(20, 8) NOT NULL,
    high_price DECIMAL(20, 8) NOT NULL,
    low_price DECIMAL(20, 8) NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    quote_volume DECIMAL(20, 8),
    num_trades INTEGER,
    open_time TIMESTAMP NOT NULL,
    close_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ohlc_pair_timeframe_close ON market_ohlc(pair, timeframe, close_time DESC);
CREATE INDEX idx_ohlc_close_time ON market_ohlc(close_time DESC);

-- Orderbook snapshots
CREATE TABLE orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    bids JSONB NOT NULL,  -- [{price, quantity}, ...]
    asks JSONB NOT NULL,
    bid_ask_spread DECIMAL(10, 6),
    market_depth_10 DECIMAL(20, 8),  -- Total volume in top 10 levels
    snapshot_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_orderbook_pair_time ON orderbook_snapshots(pair, snapshot_time DESC);

-- Aggregated trade data
CREATE TABLE market_trades (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
    trade_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_trades_pair_time ON market_trades(pair, trade_time DESC);

-- Engineered features (90 features per prediction)
CREATE TABLE engineered_features (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,

    -- High-frequency features (1min)
    hfp_rsi_1m DECIMAL(10, 6),
    hfp_macd_1m DECIMAL(15, 8),
    hfp_macd_signal_1m DECIMAL(15, 8),
    hfp_bb_upper_1m DECIMAL(20, 8),
    hfp_bb_middle_1m DECIMAL(20, 8),
    hfp_bb_lower_1m DECIMAL(20, 8),
    hfp_volume_ma_1m DECIMAL(20, 8),
    hfp_price_momentum_1m DECIMAL(10, 6),
    hfp_volatility_1m DECIMAL(10, 6),
    hfp_orderbook_imbalance DECIMAL(10, 6),
    -- ... (30 HFP features total)

    -- Medium-frequency features (5min)
    mfp_rsi_5m DECIMAL(10, 6),
    mfp_macd_5m DECIMAL(15, 8),
    mfp_macd_signal_5m DECIMAL(15, 8),
    mfp_bb_upper_5m DECIMAL(20, 8),
    mfp_bb_middle_5m DECIMAL(20, 8),
    mfp_bb_lower_5m DECIMAL(20, 8),
    mfp_atr_5m DECIMAL(15, 8),
    mfp_adx_5m DECIMAL(10, 6),
    mfp_cci_5m DECIMAL(10, 6),
    mfp_stoch_k_5m DECIMAL(10, 6),
    -- ... (30 MFP features total)

    -- Low-frequency features (15min)
    lfp_rsi_15m DECIMAL(10, 6),
    lfp_macd_15m DECIMAL(15, 8),
    lfp_ema_20_15m DECIMAL(20, 8),
    lfp_ema_50_15m DECIMAL(20, 8),
    lfp_sma_100_15m DECIMAL(20, 8),
    lfp_atr_15m DECIMAL(15, 8),
    lfp_obv_15m DECIMAL(20, 8),
    lfp_mfi_15m DECIMAL(10, 6),
    lfp_williams_r_15m DECIMAL(10, 6),
    lfp_ichimoku_tenkan_15m DECIMAL(20, 8),
    -- ... (30 LFP features total)

    -- Additional metadata
    features_vector JSONB,  -- Complete 90-feature vector as JSON array
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_features_pair_computed ON engineered_features(pair, computed_at DESC);

-- ============================================================
-- TIER 2: NEURAL NETWORK PREDICTIONS
-- ============================================================

-- ML predictions from 40M parameter model
CREATE TABLE ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    model_version VARCHAR(50) NOT NULL,

    -- Prediction output
    prediction VARCHAR(10) NOT NULL,  -- 'BUY', 'SELL', 'HOLD'
    buy_probability DECIMAL(5, 4),
    sell_probability DECIMAL(5, 4),
    hold_probability DECIMAL(5, 4),
    confidence_score DECIMAL(5, 4),

    -- Feature references
    features_id BIGINT REFERENCES engineered_features(id),

    -- Performance tracking
    actual_outcome VARCHAR(10),  -- Filled after lookback period
    correct BOOLEAN,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pred_pair_created ON ml_predictions(pair, created_at DESC);
CREATE INDEX idx_pred_correct ON ml_predictions(correct) WHERE correct IS NOT NULL;

-- Model versions and performance
CREATE TABLE ml_models (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,
    architecture VARCHAR(100),
    parameters BIGINT,
    trained_on_samples INTEGER,
    validation_accuracy DECIMAL(5, 4),
    training_loss DECIMAL(10, 6),
    validation_loss DECIMAL(10, 6),
    trained_at TIMESTAMP,
    model_path VARCHAR(255),
    scaler_path VARCHAR(255),
    active BOOLEAN DEFAULT false,
    metadata JSONB
);

-- ============================================================
-- TIER 3: AETHER DYNAMIC LEVERAGE ENGINE
-- ============================================================

-- GARCH volatility forecasts
CREATE TABLE volatility_forecasts (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,

    -- Volatility metrics
    daily_volatility DECIMAL(10, 6),
    annualized_volatility DECIMAL(10, 6),
    volatility_regime VARCHAR(20),  -- LOW, MEDIUM, HIGH, EXTREME

    -- GARCH(1,1) parameters
    garch_omega DECIMAL(15, 10),
    garch_alpha DECIMAL(10, 6),
    garch_beta DECIMAL(10, 6),
    garch_persistence DECIMAL(10, 6),

    forecast_timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_vol_pair_timestamp ON volatility_forecasts(pair, forecast_timestamp DESC);

-- Aether risk decisions (Kelly Criterion + Dynamic Leverage)
CREATE TABLE aether_risk_decisions (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    signal VARCHAR(10) NOT NULL,  -- BUY, SELL
    ml_confidence DECIMAL(5, 4),

    -- Kelly calculations
    kelly_fraction DECIMAL(10, 6),
    fractional_kelly DECIMAL(10, 6),
    volatility_adjusted_fraction DECIMAL(10, 6),

    -- Trade parameters
    position_size_zar DECIMAL(20, 2),
    leverage DECIMAL(3, 1),
    stop_loss_pct DECIMAL(6, 4),
    take_profit_pct DECIMAL(6, 4),
    max_loss_zar DECIMAL(20, 2),
    expected_gain_zar DECIMAL(20, 2),

    -- Market conditions
    daily_volatility DECIMAL(10, 6),
    volatility_regime VARCHAR(20),
    portfolio_value_zar DECIMAL(20, 2),
    drawdown_pct DECIMAL(6, 4),

    -- Outcome tracking
    executed BOOLEAN DEFAULT false,
    execution_id INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_aether_pair_created ON aether_risk_decisions(pair, created_at DESC);

-- ============================================================
-- TIER 4: LLM STRATEGIC EXECUTION LAYER
-- ============================================================

-- LLM strategic decisions
CREATE TABLE llm_strategic_decisions (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    signal VARCHAR(10) NOT NULL,
    ml_confidence DECIMAL(5, 4),

    -- Proposed trade from Tier 3
    proposed_position_size_zar DECIMAL(20, 2),
    proposed_leverage DECIMAL(3, 1),

    -- LLM analysis
    llm_decision VARCHAR(10) NOT NULL,  -- APPROVE, REJECT, MODIFY
    llm_reasoning TEXT,
    confidence_adjustment DECIMAL(5, 4),
    position_size_multiplier DECIMAL(5, 2),
    risk_flags TEXT,  -- Comma-separated flags

    -- Final outcome
    final_approved BOOLEAN,
    final_position_size_zar DECIMAL(20, 2),
    final_leverage DECIMAL(3, 1),

    -- References
    aether_decision_id BIGINT REFERENCES aether_risk_decisions(id),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_llm_decisions_pair_created ON llm_strategic_decisions(pair, created_at DESC);

-- Market context snapshots
CREATE TABLE market_context_snapshots (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,

    -- Context data
    price_action JSONB,
    correlations JSONB,
    microstructure JSONB,
    trend_regime VARCHAR(20),
    volatility_regime VARCHAR(20),
    liquidity_regime VARCHAR(20),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_context_pair_created ON market_context_snapshots(pair, created_at DESC);

-- ============================================================
-- TIER 5: GUARDIAN PORTFOLIO MANAGER
-- ============================================================

-- Portfolio state (singleton table)
CREATE TABLE portfolio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    total_value_zar DECIMAL(20, 2),
    cash_balance_zar DECIMAL(20, 2),
    positions_value_zar DECIMAL(20, 2),
    peak_value_zar DECIMAL(20, 2),
    current_drawdown_pct DECIMAL(6, 4),
    max_drawdown_pct DECIMAL(6, 4),
    daily_pnl_zar DECIMAL(20, 2),
    total_pnl_zar DECIMAL(20, 2),
    sharpe_ratio DECIMAL(10, 6),
    sortino_ratio DECIMAL(10, 6),
    win_rate DECIMAL(5, 4),
    last_updated TIMESTAMP DEFAULT NOW(),

    -- Ensure only one row
    CONSTRAINT single_row CHECK (id = 1)
);

-- Initialize portfolio
INSERT INTO portfolio_state (
    id, total_value_zar, cash_balance_zar, positions_value_zar,
    peak_value_zar, current_drawdown_pct, max_drawdown_pct
) VALUES (
    1, 100000.00, 100000.00, 0.00,
    100000.00, 0.0000, 0.0000
) ON CONFLICT (id) DO NOTHING;

-- Positions (open and closed)
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY or SELL

    -- Entry
    entry_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_value_zar DECIMAL(20, 2) NOT NULL,
    leverage DECIMAL(3, 1) DEFAULT 1.0,
    stop_loss_price DECIMAL(20, 8),
    take_profit_price DECIMAL(20, 8),
    opened_at TIMESTAMP DEFAULT NOW(),

    -- Exit
    exit_price DECIMAL(20, 8),
    exit_value_zar DECIMAL(20, 2),
    closed_at TIMESTAMP,

    -- P&L
    realized_pnl_zar DECIMAL(20, 2),
    realized_pnl_pct DECIMAL(10, 6),
    fees_zar DECIMAL(20, 2) DEFAULT 0,

    -- Status
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, CLOSED, STOPPED, LIQUIDATED

    -- References
    llm_decision_id BIGINT REFERENCES llm_strategic_decisions(id),

    -- Metadata
    metadata JSONB
);

CREATE INDEX idx_positions_pair_status ON positions(pair, status);
CREATE INDEX idx_positions_opened ON positions(opened_at DESC);
CREATE INDEX idx_positions_closed ON positions(closed_at DESC) WHERE closed_at IS NOT NULL;

-- Portfolio performance history
CREATE TABLE portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    total_value_zar DECIMAL(20, 2),
    cash_balance_zar DECIMAL(20, 2),
    positions_value_zar DECIMAL(20, 2),
    num_open_positions INTEGER,
    daily_return_pct DECIMAL(10, 6),
    cumulative_return_pct DECIMAL(10, 6),
    snapshot_time TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snapshots_time ON portfolio_snapshots(snapshot_time DESC);

-- Rebalancing history
CREATE TABLE rebalancing_events (
    id BIGSERIAL PRIMARY KEY,
    trigger VARCHAR(50),  -- 'SCHEDULED', 'DEVIATION', 'MANUAL'
    target_weights JSONB,
    actual_weights JSONB,
    changes_made JSONB,
    total_trades INTEGER,
    total_fees_zar DECIMAL(20, 2),
    executed_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- TRADING & EXECUTION
-- ============================================================

-- Order history (all orders to VALR)
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY or SELL
    order_type VARCHAR(20) NOT NULL,  -- MARKET, LIMIT, STOP_LOSS

    -- Order details
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),  -- NULL for market orders
    stop_price DECIMAL(20, 8),  -- For stop orders

    -- Execution
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    average_fill_price DECIMAL(20, 8),
    fees_zar DECIMAL(20, 2) DEFAULT 0,

    -- Status
    status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, FILLED, PARTIAL, CANCELLED, FAILED
    valr_order_id VARCHAR(100),

    -- Trading mode
    trading_mode VARCHAR(10) NOT NULL,  -- PAPER or LIVE

    -- References
    position_id BIGINT REFERENCES positions(id),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP,
    cancelled_at TIMESTAMP,

    -- Error tracking
    error_message TEXT
);

CREATE INDEX idx_orders_pair_created ON orders(pair, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_valr_id ON orders(valr_order_id) WHERE valr_order_id IS NOT NULL;

-- Trade executions (filled orders)
CREATE TABLE trade_executions (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id),
    pair VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    value_zar DECIMAL(20, 2) NOT NULL,
    fee_zar DECIMAL(20, 2) DEFAULT 0,
    trading_mode VARCHAR(10) NOT NULL,
    valr_trade_id VARCHAR(100),
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_executions_order ON trade_executions(order_id);
CREATE INDEX idx_executions_pair_time ON trade_executions(pair, executed_at DESC);

-- Balances (from VALR)
CREATE TABLE balances (
    id BIGSERIAL PRIMARY KEY,
    currency VARCHAR(20) NOT NULL,
    available DECIMAL(20, 8) NOT NULL,
    reserved DECIMAL(20, 8) DEFAULT 0,
    total DECIMAL(20, 8) NOT NULL,
    trading_mode VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_balances_currency ON balances(currency, updated_at DESC);

-- ============================================================
-- SYSTEM & MONITORING
-- ============================================================

-- System events and audit log
CREATE TABLE system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    component VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,  -- INFO, WARNING, ERROR, CRITICAL
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_events_type_created ON system_events(event_type, created_at DESC);
CREATE INDEX idx_events_component ON system_events(component, created_at DESC);

-- Trading mode history
CREATE TABLE trading_mode_history (
    id SERIAL PRIMARY KEY,
    previous_mode VARCHAR(10),
    new_mode VARCHAR(10) NOT NULL,
    reason TEXT,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP DEFAULT NOW()
);

-- Feature flag history
CREATE TABLE feature_flag_history (
    id BIGSERIAL PRIMARY KEY,
    flag_name VARCHAR(100) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP DEFAULT NOW()
);

-- Circuit breaker events
CREATE TABLE circuit_breaker_events (
    id BIGSERIAL PRIMARY KEY,
    breaker_name VARCHAR(100) NOT NULL,
    previous_state VARCHAR(20),
    new_state VARCHAR(20) NOT NULL,
    failure_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- VIEWS FOR ANALYTICS
-- ============================================================

-- Active positions view
CREATE OR REPLACE VIEW v_active_positions AS
SELECT
    p.id,
    p.pair,
    p.side,
    p.entry_price,
    p.quantity,
    p.entry_value_zar,
    p.leverage,
    p.stop_loss_price,
    p.take_profit_price,
    p.opened_at,
    o.close_price AS current_price,
    (o.close_price - p.entry_price) AS price_change,
    ((o.close_price - p.entry_price) / p.entry_price * 100) AS unrealized_pnl_pct,
    (p.quantity * (o.close_price - p.entry_price)) AS unrealized_pnl_zar
FROM positions p
LEFT JOIN LATERAL (
    SELECT close_price
    FROM market_ohlc
    WHERE pair = p.pair AND timeframe = '1m'
    ORDER BY close_time DESC
    LIMIT 1
) o ON true
WHERE p.status = 'OPEN';

-- Portfolio performance view
CREATE OR REPLACE VIEW v_portfolio_performance AS
SELECT
    DATE(snapshot_time) AS date,
    AVG(total_value_zar) AS avg_value,
    MAX(total_value_zar) AS max_value,
    MIN(total_value_zar) AS min_value,
    (MAX(total_value_zar) - MIN(total_value_zar)) / MIN(total_value_zar) * 100 AS daily_volatility_pct,
    COUNT(*) AS snapshots
FROM portfolio_snapshots
GROUP BY DATE(snapshot_time)
ORDER BY date DESC;

-- ML prediction accuracy view
CREATE OR REPLACE VIEW v_ml_accuracy AS
SELECT
    pair,
    model_version,
    COUNT(*) AS total_predictions,
    SUM(CASE WHEN correct = true THEN 1 ELSE 0 END) AS correct_predictions,
    (SUM(CASE WHEN correct = true THEN 1 ELSE 0 END)::FLOAT / COUNT(*)::FLOAT * 100) AS accuracy_pct,
    DATE(created_at) AS prediction_date
FROM ml_predictions
WHERE correct IS NOT NULL
GROUP BY pair, model_version, DATE(created_at)
ORDER BY prediction_date DESC, pair;

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

-- Update portfolio state after position changes
CREATE OR REPLACE FUNCTION update_portfolio_state()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE portfolio_state
    SET
        positions_value_zar = (
            SELECT COALESCE(SUM(entry_value_zar), 0)
            FROM positions
            WHERE status = 'OPEN'
        ),
        total_value_zar = cash_balance_zar + (
            SELECT COALESCE(SUM(entry_value_zar), 0)
            FROM positions
            WHERE status = 'OPEN'
        ),
        last_updated = NOW()
    WHERE id = 1;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_portfolio_on_position_change
AFTER INSERT OR UPDATE ON positions
FOR EACH ROW
EXECUTE FUNCTION update_portfolio_state();

-- ============================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================

-- Add additional performance indexes
CREATE INDEX idx_ohlc_pair_tf_open ON market_ohlc(pair, timeframe, open_time DESC);
CREATE INDEX idx_predictions_model_created ON ml_predictions(model_version, created_at DESC);
CREATE INDEX idx_positions_pair_opened ON positions(pair, opened_at DESC);

-- ============================================================
-- GRANTS (Run after creating user)
-- ============================================================

-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO helios;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO helios;
-- GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO helios;
