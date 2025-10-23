"""
Prometheus metrics endpoint for system monitoring.

Exposes metrics in Prometheus format for Grafana dashboards.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from datetime import datetime
import psutil
import time

router = APIRouter(tags=["Metrics"])

# Track metrics (in-memory for now)
metrics_store = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_error": 0,
    "trades_total": 0,
    "trades_success": 0,
    "trades_failed": 0,
    "websocket_connections": 0,
    "predictions_generated": 0,
    "llm_calls_total": 0,
    "start_time": time.time(),

    # Portfolio metrics
    "portfolio_value": 100000.0,
    "portfolio_total_pnl": 0.0,
    "portfolio_daily_pnl": 0.0,
    "sharpe_ratio": 0.0,
    "max_drawdown_percent": 0.0,
    "current_drawdown_percent": 0.0,

    # ML metrics
    "ml_predictions_total": 0,
    "ml_model_accuracy": 0.0,
    "ml_confidence_avg": 0.0,
    "ml_confidence_high": 0,
    "ml_confidence_low": 0,
    "ml_predictions_correct": 0,
    "ml_predictions_incorrect": 0,
    "ml_predictions_buy": 0,
    "ml_predictions_sell": 0,
    "ml_predictions_hold": 0,
    "ml_lstm_loss": 0.0,
    "ml_feature_importance": 0.0,
    "ml_inference_time_ms": 0.0,
    "ml_training_epochs": 0,
    "ml_validation_loss": 0.0,

    # Risk metrics
    "var_95": 0.0,
    "var_99": 0.0,
    "expected_shortfall": 0.0,
    "position_concentration": 0.0,
    "portfolio_volatility": 0.0,
    "correlation_btc_eth": 0.0,
    "aether_risk_score": 0,
    "position_size_btc": 0.0,
    "position_size_eth": 0.0,
    "risk_limit_used": 0.0,
    "risk_limit_total": 100000.0,
    "emergency_stop_active": 0,

    # Tier health
    "tier1_healthy": 1,
    "tier2_healthy": 1,
    "tier3_healthy": 1,
    "tier4_healthy": 1,
    "tier5_healthy": 1,
}


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    """
    uptime = time.time() - metrics_store["start_time"]

    # System metrics
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    memory_percent = memory.percent

    # Build Prometheus format response
    metrics = []

    # Help and type definitions
    metrics.append("# HELP helios_uptime_seconds System uptime in seconds")
    metrics.append("# TYPE helios_uptime_seconds gauge")
    metrics.append(f"helios_uptime_seconds {uptime:.2f}")

    metrics.append("# HELP helios_cpu_usage_percent CPU usage percentage")
    metrics.append("# TYPE helios_cpu_usage_percent gauge")
    metrics.append(f"helios_cpu_usage_percent {cpu_percent}")

    metrics.append("# HELP helios_memory_usage_percent Memory usage percentage")
    metrics.append("# TYPE helios_memory_usage_percent gauge")
    metrics.append(f"helios_memory_usage_percent {memory_percent}")

    # Request metrics
    metrics.append("# HELP helios_requests_total Total number of requests")
    metrics.append("# TYPE helios_requests_total counter")
    metrics.append(f"helios_requests_total {metrics_store['requests_total']}")

    metrics.append("# HELP helios_requests_success_total Successful requests")
    metrics.append("# TYPE helios_requests_success_total counter")
    metrics.append(f"helios_requests_success_total {metrics_store['requests_success']}")

    metrics.append("# HELP helios_requests_error_total Failed requests")
    metrics.append("# TYPE helios_requests_error_total counter")
    metrics.append(f"helios_requests_error_total {metrics_store['requests_error']}")

    # Trading metrics
    metrics.append("# HELP helios_trades_total Total number of trades")
    metrics.append("# TYPE helios_trades_total counter")
    metrics.append(f"helios_trades_total {metrics_store['trades_total']}")

    metrics.append("# HELP helios_trades_success_total Successful trades")
    metrics.append("# TYPE helios_trades_success_total counter")
    metrics.append(f"helios_trades_success_total {metrics_store['trades_success']}")

    metrics.append("# HELP helios_trades_failed_total Failed trades")
    metrics.append("# TYPE helios_trades_failed_total counter")
    metrics.append(f"helios_trades_failed_total {metrics_store['trades_failed']}")

    # WebSocket metrics
    metrics.append("# HELP helios_websocket_connections Active WebSocket connections")
    metrics.append("# TYPE helios_websocket_connections gauge")
    metrics.append(f"helios_websocket_connections {metrics_store['websocket_connections']}")

    # ML metrics
    metrics.append("# HELP helios_predictions_generated_total Neural network predictions generated")
    metrics.append("# TYPE helios_predictions_generated_total counter")
    metrics.append(f"helios_predictions_generated_total {metrics_store['predictions_generated']}")

    # LLM metrics
    metrics.append("# HELP helios_llm_calls_total LLM API calls")
    metrics.append("# TYPE helios_llm_calls_total counter")
    metrics.append(f"helios_llm_calls_total {metrics_store['llm_calls_total']}")

    # Portfolio metrics
    metrics.append("# HELP helios_portfolio_value Portfolio value in ZAR")
    metrics.append("# TYPE helios_portfolio_value gauge")
    metrics.append(f"helios_portfolio_value {metrics_store['portfolio_value']}")

    metrics.append("# HELP helios_portfolio_total_pnl Total P&L in ZAR")
    metrics.append("# TYPE helios_portfolio_total_pnl gauge")
    metrics.append(f"helios_portfolio_total_pnl {metrics_store['portfolio_total_pnl']}")

    metrics.append("# HELP helios_portfolio_daily_pnl Daily P&L in ZAR")
    metrics.append("# TYPE helios_portfolio_daily_pnl gauge")
    metrics.append(f"helios_portfolio_daily_pnl {metrics_store['portfolio_daily_pnl']}")

    metrics.append("# HELP helios_sharpe_ratio Sharpe ratio")
    metrics.append("# TYPE helios_sharpe_ratio gauge")
    metrics.append(f"helios_sharpe_ratio {metrics_store['sharpe_ratio']}")

    metrics.append("# HELP helios_max_drawdown_percent Maximum drawdown percentage")
    metrics.append("# TYPE helios_max_drawdown_percent gauge")
    metrics.append(f"helios_max_drawdown_percent {metrics_store['max_drawdown_percent']}")

    metrics.append("# HELP helios_current_drawdown_percent Current drawdown percentage")
    metrics.append("# TYPE helios_current_drawdown_percent gauge")
    metrics.append(f"helios_current_drawdown_percent {metrics_store['current_drawdown_percent']}")

    # ML metrics
    metrics.append("# HELP helios_ml_predictions_total Total ML predictions")
    metrics.append("# TYPE helios_ml_predictions_total counter")
    metrics.append(f"helios_ml_predictions_total {metrics_store['ml_predictions_total']}")

    metrics.append("# HELP helios_ml_model_accuracy Model accuracy percentage")
    metrics.append("# TYPE helios_ml_model_accuracy gauge")
    metrics.append(f"helios_ml_model_accuracy {metrics_store['ml_model_accuracy']}")

    metrics.append("# HELP helios_ml_confidence_avg Average prediction confidence")
    metrics.append("# TYPE helios_ml_confidence_avg gauge")
    metrics.append(f"helios_ml_confidence_avg {metrics_store['ml_confidence_avg']}")

    metrics.append("# HELP helios_ml_confidence_high High confidence predictions")
    metrics.append("# TYPE helios_ml_confidence_high counter")
    metrics.append(f"helios_ml_confidence_high {metrics_store['ml_confidence_high']}")

    metrics.append("# HELP helios_ml_confidence_low Low confidence predictions")
    metrics.append("# TYPE helios_ml_confidence_low counter")
    metrics.append(f"helios_ml_confidence_low {metrics_store['ml_confidence_low']}")

    metrics.append("# HELP helios_ml_predictions_correct Correct predictions")
    metrics.append("# TYPE helios_ml_predictions_correct counter")
    metrics.append(f"helios_ml_predictions_correct {metrics_store['ml_predictions_correct']}")

    metrics.append("# HELP helios_ml_predictions_incorrect Incorrect predictions")
    metrics.append("# TYPE helios_ml_predictions_incorrect counter")
    metrics.append(f"helios_ml_predictions_incorrect {metrics_store['ml_predictions_incorrect']}")

    metrics.append("# HELP helios_ml_predictions_buy BUY signal predictions")
    metrics.append("# TYPE helios_ml_predictions_buy counter")
    metrics.append(f"helios_ml_predictions_buy {metrics_store['ml_predictions_buy']}")

    metrics.append("# HELP helios_ml_predictions_sell SELL signal predictions")
    metrics.append("# TYPE helios_ml_predictions_sell counter")
    metrics.append(f"helios_ml_predictions_sell {metrics_store['ml_predictions_sell']}")

    metrics.append("# HELP helios_ml_predictions_hold HOLD signal predictions")
    metrics.append("# TYPE helios_ml_predictions_hold counter")
    metrics.append(f"helios_ml_predictions_hold {metrics_store['ml_predictions_hold']}")

    metrics.append("# HELP helios_ml_lstm_loss LSTM model loss")
    metrics.append("# TYPE helios_ml_lstm_loss gauge")
    metrics.append(f"helios_ml_lstm_loss {metrics_store['ml_lstm_loss']}")

    metrics.append("# HELP helios_ml_feature_importance Feature importance score")
    metrics.append("# TYPE helios_ml_feature_importance gauge")
    metrics.append(f"helios_ml_feature_importance {metrics_store['ml_feature_importance']}")

    metrics.append("# HELP helios_ml_inference_time_ms Model inference time in ms")
    metrics.append("# TYPE helios_ml_inference_time_ms gauge")
    metrics.append(f"helios_ml_inference_time_ms {metrics_store['ml_inference_time_ms']}")

    metrics.append("# HELP helios_ml_training_epochs Training epochs completed")
    metrics.append("# TYPE helios_ml_training_epochs gauge")
    metrics.append(f"helios_ml_training_epochs {metrics_store['ml_training_epochs']}")

    metrics.append("# HELP helios_ml_validation_loss Validation loss")
    metrics.append("# TYPE helios_ml_validation_loss gauge")
    metrics.append(f"helios_ml_validation_loss {metrics_store['ml_validation_loss']}")

    # Risk metrics
    metrics.append("# HELP helios_var_95 Value at Risk 95th percentile")
    metrics.append("# TYPE helios_var_95 gauge")
    metrics.append(f"helios_var_95 {metrics_store['var_95']}")

    metrics.append("# HELP helios_var_99 Value at Risk 99th percentile")
    metrics.append("# TYPE helios_var_99 gauge")
    metrics.append(f"helios_var_99 {metrics_store['var_99']}")

    metrics.append("# HELP helios_expected_shortfall Expected shortfall")
    metrics.append("# TYPE helios_expected_shortfall gauge")
    metrics.append(f"helios_expected_shortfall {metrics_store['expected_shortfall']}")

    metrics.append("# HELP helios_position_concentration Position concentration risk")
    metrics.append("# TYPE helios_position_concentration gauge")
    metrics.append(f"helios_position_concentration {metrics_store['position_concentration']}")

    metrics.append("# HELP helios_portfolio_volatility Portfolio volatility")
    metrics.append("# TYPE helios_portfolio_volatility gauge")
    metrics.append(f"helios_portfolio_volatility {metrics_store['portfolio_volatility']}")

    metrics.append("# HELP helios_correlation_btc_eth BTC-ETH correlation")
    metrics.append("# TYPE helios_correlation_btc_eth gauge")
    metrics.append(f"helios_correlation_btc_eth {metrics_store['correlation_btc_eth']}")

    metrics.append("# HELP helios_aether_risk_score Aether risk score (0-100)")
    metrics.append("# TYPE helios_aether_risk_score gauge")
    metrics.append(f"helios_aether_risk_score {metrics_store['aether_risk_score']}")

    metrics.append("# HELP helios_position_size_btc BTC position size")
    metrics.append("# TYPE helios_position_size_btc gauge")
    metrics.append(f"helios_position_size_btc {metrics_store['position_size_btc']}")

    metrics.append("# HELP helios_position_size_eth ETH position size")
    metrics.append("# TYPE helios_position_size_eth gauge")
    metrics.append(f"helios_position_size_eth {metrics_store['position_size_eth']}")

    metrics.append("# HELP helios_risk_limit_used Risk limit used")
    metrics.append("# TYPE helios_risk_limit_used gauge")
    metrics.append(f"helios_risk_limit_used {metrics_store['risk_limit_used']}")

    metrics.append("# HELP helios_risk_limit_total Total risk limit")
    metrics.append("# TYPE helios_risk_limit_total gauge")
    metrics.append(f"helios_risk_limit_total {metrics_store['risk_limit_total']}")

    metrics.append("# HELP helios_emergency_stop_active Emergency stop status (0=active, 1=stopped)")
    metrics.append("# TYPE helios_emergency_stop_active gauge")
    metrics.append(f"helios_emergency_stop_active {metrics_store['emergency_stop_active']}")

    # Tier health
    metrics.append("# HELP helios_tier1_healthy Tier 1 health status")
    metrics.append("# TYPE helios_tier1_healthy gauge")
    metrics.append(f"helios_tier1_healthy {metrics_store['tier1_healthy']}")

    metrics.append("# HELP helios_tier2_healthy Tier 2 health status")
    metrics.append("# TYPE helios_tier2_healthy gauge")
    metrics.append(f"helios_tier2_healthy {metrics_store['tier2_healthy']}")

    metrics.append("# HELP helios_tier3_healthy Tier 3 health status")
    metrics.append("# TYPE helios_tier3_healthy gauge")
    metrics.append(f"helios_tier3_healthy {metrics_store['tier3_healthy']}")

    metrics.append("# HELP helios_tier4_healthy Tier 4 health status")
    metrics.append("# TYPE helios_tier4_healthy gauge")
    metrics.append(f"helios_tier4_healthy {metrics_store['tier4_healthy']}")

    metrics.append("# HELP helios_tier5_healthy Tier 5 health status")
    metrics.append("# TYPE helios_tier5_healthy gauge")
    metrics.append(f"helios_tier5_healthy {metrics_store['tier5_healthy']}")

    return "\n".join(metrics)


# Helper functions to increment metrics
def increment_request():
    metrics_store["requests_total"] += 1

def increment_request_success():
    metrics_store["requests_success"] += 1

def increment_request_error():
    metrics_store["requests_error"] += 1

def increment_trade():
    metrics_store["trades_total"] += 1

def increment_trade_success():
    metrics_store["trades_success"] += 1

def increment_trade_failed():
    metrics_store["trades_failed"] += 1

def increment_prediction():
    metrics_store["predictions_generated"] += 1

def increment_llm_call():
    metrics_store["llm_calls_total"] += 1

def set_websocket_connections(count: int):
    metrics_store["websocket_connections"] = count
