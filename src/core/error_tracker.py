"""
Error Tracking System
Centralized error collection with context
"""

from datetime import datetime
from typing import Dict, List, Optional
import traceback
from collections import deque


class ErrorTracker:
    """Track errors with context for debugging"""

    def __init__(self, max_errors: int = 500):
        self.errors = deque(maxlen=max_errors)
        self.error_counts = {}

    def track_error(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        component: str = "unknown"
    ):
        """Track error with context"""
        error_type = type(error).__name__

        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "component": component,
            "type": error_type,
            "message": str(error),
            "context": context or {},
            "traceback": traceback.format_exc()
        }

        self.errors.append(error_entry)

        # Count by type
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1

        return error_entry

    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """Get most recent errors"""
        return list(self.errors)[-limit:]

    def get_error_summary(self) -> Dict:
        """Get error statistics"""
        return {
            "total_errors": len(self.errors),
            "by_type": dict(self.error_counts),
            "recent_count": len([e for e in self.errors if self._is_recent(e["timestamp"])])
        }

    def _is_recent(self, timestamp_str: str, minutes: int = 5) -> bool:
        """Check if timestamp is within last N minutes"""
        try:
            ts = datetime.fromisoformat(timestamp_str)
            now = datetime.utcnow()
            return (now - ts).total_seconds() < (minutes * 60)
        except:
            return False

    def clear_errors(self):
        """Clear all tracked errors"""
        self.errors.clear()
        self.error_counts.clear()


# Global error tracker instance
error_tracker = ErrorTracker()
