"""
Debug & Monitoring Endpoints
Provides visibility into system internals for error analysis
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Optional

from src.core.error_tracker import error_tracker
from src.core.activity_tracker import activity_tracker

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/recent-errors")
async def get_recent_errors(limit: int = 50):
    """
    Get recent errors from error tracker

    This endpoint exposes errors that have been tracked across the system,
    making it easy to diagnose issues without checking logs.
    """
    try:
        errors = error_tracker.get_recent_errors(limit)
        summary = error_tracker.get_error_summary()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "errors": errors,
            "summary": summary,
            "count": len(errors)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activity-log")
async def get_activity_log(limit: int = 100, activity_type: Optional[str] = None):
    """
    Get recent system activities

    This is the data source for the dashboard activity log.
    Shows what the system is doing in real-time.
    """
    try:
        if activity_type:
            activities = activity_tracker.get_activities_by_type(activity_type, limit)
        else:
            activities = activity_tracker.get_recent_activities(limit)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "activities": activities,
            "count": len(activities),
            "filter": activity_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/error-summary")
async def get_error_summary():
    """
    Get error statistics

    Quick overview of error types and counts
    """
    try:
        summary = error_tracker.get_error_summary()
        return {
            "timestamp": datetime.utcnow().isoformat(),
            **summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-errors")
async def clear_errors():
    """Clear all tracked errors"""
    try:
        error_tracker.clear_errors()
        return {
            "status": "success",
            "message": "All errors cleared",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-activities")
async def clear_activities():
    """Clear all tracked activities"""
    try:
        activity_tracker.clear_activities()
        return {
            "status": "success",
            "message": "All activities cleared",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-check")
async def debug_health_check():
    """
    Health check for debug endpoints

    Verifies that error tracking and activity tracking are working
    """
    return {
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "error_tracker": {
            "total_errors": len(error_tracker.errors),
            "max_capacity": error_tracker.errors.maxlen
        },
        "activity_tracker": {
            "total_activities": len(activity_tracker.activities),
            "max_capacity": activity_tracker.activities.maxlen
        }
    }
