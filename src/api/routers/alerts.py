"""
Alert system API endpoints.

Provides endpoints for viewing alert history and testing notifications.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from src.alerts.alert_manager import alert_manager, AlertLevel, Alert
from src.alerts.alert_rules import send_test_alert

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class AlertResponse(BaseModel):
    """Alert response model."""
    level: str
    title: str
    message: str
    source: str
    timestamp: str
    metadata: dict


class AlertHistoryResponse(BaseModel):
    """Alert history response."""
    total: int
    alerts: List[AlertResponse]


@router.get("/history", response_model=AlertHistoryResponse)
async def get_alert_history(
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100
):
    """
    Get alert history with optional filters.

    Args:
        level: Filter by alert level (info, warning, critical)
        source: Filter by source (system, tier1, tier2, tier3, tier4, tier5, portfolio)
        limit: Maximum number of alerts to return (default: 100)

    Returns:
        Alert history with total count
    """
    # Parse level filter
    level_filter = None
    if level:
        try:
            level_filter = AlertLevel(level.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level: {level}. Must be one of: info, warning, critical"
            )

    # Get filtered alerts
    alerts = alert_manager.get_alert_history(
        level=level_filter,
        source=source,
        limit=limit
    )

    # Convert to response format
    alert_responses = [
        AlertResponse(
            level=alert.level.value,
            title=alert.title,
            message=alert.message,
            source=alert.source,
            timestamp=alert.timestamp.isoformat(),
            metadata=alert.metadata or {}
        )
        for alert in alerts
    ]

    return AlertHistoryResponse(
        total=len(alert_responses),
        alerts=alert_responses
    )


@router.get("/active", response_model=AlertHistoryResponse)
async def get_active_alerts():
    """
    Get active alerts (last 24 hours).

    Returns:
        Active alerts from the last 24 hours
    """
    alerts = alert_manager.get_active_alerts()

    alert_responses = [
        AlertResponse(
            level=alert.level.value,
            title=alert.title,
            message=alert.message,
            source=alert.source,
            timestamp=alert.timestamp.isoformat(),
            metadata=alert.metadata or {}
        )
        for alert in alerts
    ]

    return AlertHistoryResponse(
        total=len(alert_responses),
        alerts=alert_responses
    )


@router.post("/test")
async def test_alert_system():
    """
    Send a test alert to verify notification channels.

    This will send a test alert via all configured notification channels
    (email, SMS, etc.) to verify they are working correctly.

    Returns:
        Success message
    """
    try:
        await send_test_alert()
        return {
            "success": True,
            "message": "Test alert sent successfully",
            "channels": len(alert_manager.notifiers),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test alert: {str(e)}"
        )


@router.get("/config")
async def get_alert_config():
    """
    Get alert system configuration.

    Returns:
        Alert system configuration details
    """
    return {
        "rules": len(alert_manager.rules),
        "notifiers": [notifier.__class__.__name__ for notifier in alert_manager.notifiers],
        "history_size": len(alert_manager.alert_history),
        "max_history": alert_manager.max_history,
        "throttle_window_seconds": alert_manager.throttle_window.total_seconds()
    }


@router.delete("/history")
async def clear_alert_history():
    """
    Clear alert history (admin function).

    Use with caution - this will delete all alert history.

    Returns:
        Success message
    """
    alert_manager.clear_history()
    return {
        "success": True,
        "message": "Alert history cleared",
        "timestamp": datetime.utcnow().isoformat()
    }
