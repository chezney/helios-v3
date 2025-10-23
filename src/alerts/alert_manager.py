"""
Central alert management system.

Handles alert routing, throttling, and distribution to notification channels.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert data structure."""
    level: AlertLevel
    title: str
    message: str
    source: str  # e.g., "tier3", "portfolio", "system"
    timestamp: datetime
    metadata: Dict = None


class AlertManager:
    """
    Manages alert creation, throttling, and distribution.

    Features:
    - Alert throttling (prevent spam)
    - Multi-channel distribution (email, SMS)
    - Alert history tracking
    - Configurable rules
    """

    def __init__(self):
        self.notifiers = []
        self.alert_history: List[Alert] = []
        self.recent_alerts: Dict[str, datetime] = {}  # For throttling
        self.throttle_window = timedelta(minutes=5)  # Don't repeat same alert within 5 min
        self.max_history = 1000

        # Alert rules: (check_function, title, message, level, source)
        self.rules = []

    def add_notifier(self, notifier):
        """Add a notification channel (email, SMS, etc.)."""
        self.notifiers.append(notifier)
        logger.info(f"Added notifier: {notifier.__class__.__name__}")

    def add_rule(self, check_fn, title: str, message: str, level: AlertLevel, source: str):
        """
        Add an alert rule.

        Args:
            check_fn: Function that returns True if alert should fire
            title: Alert title
            message: Alert message
            level: Alert severity level
            source: Alert source identifier
        """
        self.rules.append({
            "check": check_fn,
            "title": title,
            "message": message,
            "level": level,
            "source": source
        })
        logger.info(f"Added alert rule: {title} [{level.value}]")

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        source: str,
        metadata: Optional[Dict] = None
    ):
        """
        Send an alert to all configured notifiers.

        Implements throttling to prevent alert spam.
        """
        # Create alert object
        alert = Alert(
            level=level,
            title=title,
            message=message,
            source=source,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )

        # Check if this alert was recently sent (throttling)
        alert_key = f"{source}:{title}"
        if alert_key in self.recent_alerts:
            last_sent = self.recent_alerts[alert_key]
            if datetime.utcnow() - last_sent < self.throttle_window:
                logger.debug(f"Throttled alert: {title} (sent {datetime.utcnow() - last_sent} ago)")
                return

        # Update recent alerts
        self.recent_alerts[alert_key] = datetime.utcnow()

        # Add to history
        self.alert_history.append(alert)
        if len(self.alert_history) > self.max_history:
            self.alert_history.pop(0)

        # Log alert
        log_msg = f"[{level.value.upper()}] {title}: {message}"
        if level == AlertLevel.CRITICAL:
            logger.critical(log_msg)
        elif level == AlertLevel.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Send to all notifiers
        for notifier in self.notifiers:
            try:
                await notifier.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {notifier.__class__.__name__}: {e}")

        logger.info(f"Alert sent: {title} [{level.value}] via {len(self.notifiers)} channels")

    async def check_all_rules(self):
        """
        Check all registered alert rules.

        Run this periodically (e.g., every 30 seconds) to evaluate conditions.
        """
        for rule in self.rules:
            try:
                # Check if condition is met
                if rule["check"]():
                    await self.send_alert(
                        level=rule["level"],
                        title=rule["title"],
                        message=rule["message"],
                        source=rule["source"]
                    )
            except Exception as e:
                logger.error(f"Error checking rule '{rule['title']}': {e}")

    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        source: Optional[str] = None,
        limit: int = 100
    ) -> List[Alert]:
        """
        Get alert history with optional filters.

        Args:
            level: Filter by alert level
            source: Filter by source
            limit: Maximum number of alerts to return

        Returns:
            List of alerts (most recent first)
        """
        filtered = self.alert_history

        if level:
            filtered = [a for a in filtered if a.level == level]
        if source:
            filtered = [a for a in filtered if a.source == source]

        # Return most recent first
        return list(reversed(filtered[-limit:]))

    def get_active_alerts(self) -> List[Alert]:
        """Get alerts from the last 24 hours."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return [a for a in self.alert_history if a.timestamp > cutoff]

    def clear_history(self):
        """Clear alert history (for testing or maintenance)."""
        self.alert_history.clear()
        self.recent_alerts.clear()
        logger.info("Alert history cleared")


# Global alert manager instance
alert_manager = AlertManager()
