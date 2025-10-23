"""
Activity Tracking System
Log user-visible activities for dashboard display
"""

from datetime import datetime
from typing import Dict, List, Optional
from collections import deque


class ActivityTracker:
    """Track system activities for user visibility"""

    def __init__(self, max_activities: int = 500):
        self.activities = deque(maxlen=max_activities)

    def log_activity(
        self,
        activity_type: str,
        message: str,
        details: Optional[Dict] = None,
        severity: str = "INFO"
    ):
        """Log an activity"""
        activity = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": activity_type,
            "severity": severity,
            "message": message,
            "details": details or {}
        }

        self.activities.append(activity)
        return activity

    def get_recent_activities(self, limit: int = 100) -> List[Dict]:
        """Get most recent activities"""
        return list(self.activities)[-limit:]

    def get_activities_by_type(self, activity_type: str, limit: int = 50) -> List[Dict]:
        """Get activities of specific type"""
        filtered = [a for a in self.activities if a["type"] == activity_type]
        return filtered[-limit:]

    def clear_activities(self):
        """Clear all activities"""
        self.activities.clear()


# Global activity tracker instance
activity_tracker = ActivityTracker()
