"""
Alert rules for Helios V3.0 Trading System.

Defines conditions that trigger alerts across all system tiers.
"""

from .alert_manager import AlertLevel, alert_manager
from src.api.routers.metrics import metrics_store
import logging

logger = logging.getLogger(__name__)


def setup_default_alert_rules():
    """
    Configure default alert rules for the trading system.

    Rules are checked periodically by the alert manager.
    """

    # ========== SYSTEM HEALTH ALERTS ==========

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("cpu_usage_percent", 0) > 80,
        title="High CPU Usage",
        message=f"CPU usage is {metrics_store.get('cpu_usage_percent', 0):.1f}% (threshold: 80%)",
        level=AlertLevel.WARNING,
        source="system"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("cpu_usage_percent", 0) > 95,
        title="Critical CPU Usage",
        message=f"CPU usage is {metrics_store.get('cpu_usage_percent', 0):.1f}% (threshold: 95%) - system may be overloaded",
        level=AlertLevel.CRITICAL,
        source="system"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("memory_usage_percent", 0) > 85,
        title="High Memory Usage",
        message=f"Memory usage is {metrics_store.get('memory_usage_percent', 0):.1f}% (threshold: 85%)",
        level=AlertLevel.WARNING,
        source="system"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("memory_usage_percent", 0) > 95,
        title="Critical Memory Usage",
        message=f"Memory usage is {metrics_store.get('memory_usage_percent', 0):.1f}% (threshold: 95%) - system may crash",
        level=AlertLevel.CRITICAL,
        source="system"
    )

    # ========== TRADING PERFORMANCE ALERTS ==========

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("portfolio_daily_pnl", 0) < -5000,
        title="Large Daily Loss",
        message=f"Daily P&L is R{metrics_store.get('portfolio_daily_pnl', 0):.2f} (threshold: -R5,000)",
        level=AlertLevel.WARNING,
        source="portfolio"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("portfolio_daily_pnl", 0) < -10000,
        title="Critical Daily Loss",
        message=f"Daily P&L is R{metrics_store.get('portfolio_daily_pnl', 0):.2f} (threshold: -R10,000) - consider emergency stop",
        level=AlertLevel.CRITICAL,
        source="portfolio"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("current_drawdown_percent", 0) > 15,
        title="High Drawdown",
        message=f"Current drawdown is {metrics_store.get('current_drawdown_percent', 0):.1f}% (threshold: 15%)",
        level=AlertLevel.WARNING,
        source="portfolio"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("current_drawdown_percent", 0) > 20,
        title="Critical Drawdown",
        message=f"Current drawdown is {metrics_store.get('current_drawdown_percent', 0):.1f}% (threshold: 20%) - EMERGENCY STOP RECOMMENDED",
        level=AlertLevel.CRITICAL,
        source="portfolio"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("max_drawdown_percent", 0) > 25,
        title="Excessive Max Drawdown",
        message=f"Max drawdown is {metrics_store.get('max_drawdown_percent', 0):.1f}% (threshold: 25%) - review risk management",
        level=AlertLevel.CRITICAL,
        source="portfolio"
    )

    # ========== RISK MANAGEMENT ALERTS ==========

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("var_95", 0) > 10000,
        title="High Value at Risk",
        message=f"VaR (95%) is R{metrics_store.get('var_95', 0):.2f} (threshold: R10,000)",
        level=AlertLevel.WARNING,
        source="tier3"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("var_95", 0) > 15000,
        title="Critical Value at Risk",
        message=f"VaR (95%) is R{metrics_store.get('var_95', 0):.2f} (threshold: R15,000) - CRITICAL RISK LEVEL",
        level=AlertLevel.CRITICAL,
        source="tier3"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("position_concentration", 0) > 50,
        title="High Position Concentration",
        message=f"Position concentration is {metrics_store.get('position_concentration', 0):.1f}% (threshold: 50%) - diversification needed",
        level=AlertLevel.WARNING,
        source="tier3"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("aether_risk_score", 0) > 80,
        title="High Aether Risk Score",
        message=f"Aether risk score is {metrics_store.get('aether_risk_score', 0)} (threshold: 80) - consider reducing exposure",
        level=AlertLevel.WARNING,
        source="tier3"
    )

    alert_manager.add_rule(
        check_fn=lambda: (metrics_store.get("risk_limit_used", 0) / max(metrics_store.get("risk_limit_total", 1), 1)) > 0.90,
        title="High Risk Limit Utilization",
        message=f"Risk limit utilization is {(metrics_store.get('risk_limit_used', 0) / max(metrics_store.get('risk_limit_total', 1), 1) * 100):.1f}% (threshold: 90%) - reduce positions",
        level=AlertLevel.WARNING,
        source="tier3"
    )

    # ========== ML MODEL ALERTS ==========

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("ml_model_accuracy", 100) < 50,
        title="Low Model Accuracy",
        message=f"ML model accuracy is {metrics_store.get('ml_model_accuracy', 0):.1f}% (threshold: 50%) - model may need retraining",
        level=AlertLevel.WARNING,
        source="tier2"
    )

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("ml_inference_time_ms", 0) > 500,
        title="Slow Model Inference",
        message=f"ML inference time is {metrics_store.get('ml_inference_time_ms', 0):.0f}ms (threshold: 500ms) - performance degradation",
        level=AlertLevel.WARNING,
        source="tier2"
    )

    # ========== TIER HEALTH ALERTS ==========

    for tier_num in range(1, 6):
        tier_key = f"tier{tier_num}_healthy"
        alert_manager.add_rule(
            check_fn=lambda t=tier_num, k=tier_key: metrics_store.get(k, 1) == 0,
            title=f"Tier {tier_num} Unhealthy",
            message=f"Tier {tier_num} health check failed - immediate attention required",
            level=AlertLevel.CRITICAL,
            source=f"tier{tier_num}"
        )

    # ========== EMERGENCY STOP ALERT ==========

    alert_manager.add_rule(
        check_fn=lambda: metrics_store.get("emergency_stop_active", 0) == 1,
        title="Emergency Stop Activated",
        message="Emergency stop has been triggered - all trading halted",
        level=AlertLevel.CRITICAL,
        source="system"
    )

    # ========== REQUEST ERROR RATE ALERT ==========

    def check_error_rate():
        total = metrics_store.get("requests_total", 0)
        errors = metrics_store.get("requests_error", 0)
        if total > 100:  # Only check if we have enough requests
            error_rate = (errors / total) * 100
            return error_rate > 5  # 5% error rate
        return False

    alert_manager.add_rule(
        check_fn=check_error_rate,
        title="High API Error Rate",
        message=f"API error rate is above 5% - check system logs",
        level=AlertLevel.WARNING,
        source="system"
    )

    logger.info(f"Configured {len(alert_manager.rules)} default alert rules")


# Helper function to manually trigger test alerts
async def send_test_alert():
    """Send a test alert to verify notification channels."""
    await alert_manager.send_alert(
        level=AlertLevel.INFO,
        title="Alert System Test",
        message="This is a test alert to verify that notification channels are working correctly. If you received this, the alert system is operational!",
        source="system",
        metadata={
            "test": True,
            "timestamp": "2025-10-06"
        }
    )
    logger.info("Test alert sent")
