# Observability & Monitoring Infrastructure Skill

## Purpose
Create structured logging and monitoring endpoints that expose system state for error analysis and debugging.

## What This Skill Does

1. **Create Debug Endpoints** - API endpoints that expose internal system state
2. **Add Structured Logging** - Consistent log format with context
3. **Create Activity Log** - User-facing activity stream
4. **Add Error Tracking** - Centralized error collection
5. **Create Health Checks** - Detailed component status endpoints

## Implementation Steps

### 1. Create Debug Endpoints

Add these endpoints to expose system internals:

```python
# src/api/routers/debug.py
from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/api/debug", tags=["debug"])

@router.get("/recent-errors")
async def get_recent_errors(limit: int = 50):
    """Get last N errors from all components"""
    return {
        "errors": ERROR_BUFFER[-limit:],
        "count": len(ERROR_BUFFER)
    }

@router.get("/recent-requests")
async def get_recent_requests(limit: int = 100):
    """Get last N API requests"""
    return {
        "requests": REQUEST_LOG[-limit:],
        "count": len(REQUEST_LOG)
    }

@router.get("/component-status")
async def get_component_status():
    """Get detailed status of each component"""
    return {
        "tier1_data_collection": check_tier1_status(),
        "tier2_ml_predictions": check_tier2_status(),
        "tier3_risk_engine": check_tier3_status(),
        "tier4_llm_strategy": check_tier4_status(),
        "tier5_portfolio": check_tier5_status(),
        "autonomous_engine": check_engine_status()
    }
```

### 2. Add Activity Log Endpoint

Create user-facing activity stream:

```python
@router.get("/activity-log")
async def get_activity_log(limit: int = 100):
    """Get recent system activity for dashboard"""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "activities": ACTIVITY_BUFFER[-limit:],
        "count": len(ACTIVITY_BUFFER)
    }
```

### 3. Add Request Logging Middleware

Track all API requests:

```python
# src/api/middleware/request_logger.py
from fastapi import Request
import time

REQUEST_LOG = []

async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    REQUEST_LOG.append({
        "timestamp": datetime.utcnow().isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration * 1000
    })

    # Keep only last 1000 requests
    if len(REQUEST_LOG) > 1000:
        REQUEST_LOG.pop(0)

    return response
```

### 4. Add Error Tracking

Centralized error collection:

```python
# src/core/error_tracker.py
ERROR_BUFFER = []

def track_error(error: Exception, context: dict = None):
    """Track error with context"""
    ERROR_BUFFER.append({
        "timestamp": datetime.utcnow().isoformat(),
        "type": type(error).__name__,
        "message": str(error),
        "context": context or {},
        "traceback": traceback.format_exc()
    })

    # Keep only last 500 errors
    if len(ERROR_BUFFER) > 500:
        ERROR_BUFFER.pop(0)
```

### 5. Add Activity Tracking

Log user-visible activities:

```python
# src/core/activity_tracker.py
ACTIVITY_BUFFER = []

def log_activity(activity_type: str, message: str, details: dict = None):
    """Log activity for dashboard display"""
    ACTIVITY_BUFFER.append({
        "timestamp": datetime.utcnow().isoformat(),
        "type": activity_type,
        "message": message,
        "details": details or {}
    })

    # Keep only last 500 activities
    if len(ACTIVITY_BUFFER) > 500:
        ACTIVITY_BUFFER.pop(0)

# Usage examples:
log_activity("TRADE", "Executed BUY BTCZAR @ R1,234,567", {"pair": "BTCZAR", "side": "BUY"})
log_activity("PREDICTION", "ML confidence: 78% BUY", {"pair": "BTCZAR", "confidence": 0.78})
log_activity("ERROR", "Portfolio fetch failed", {"endpoint": "/api/portfolio/summary"})
```

### 6. Enhance Health Check

Make health check more detailed:

```python
@router.get("/system/health/detailed")
async def detailed_health():
    """Detailed health with component-specific info"""
    return {
        "overall": "healthy" if all_healthy() else "degraded",
        "components": {
            "database": {
                "status": "connected",
                "latency_ms": measure_db_latency(),
                "pool_size": get_pool_size()
            },
            "tier1": {
                "status": "collecting",
                "last_candle": get_last_candle_time(),
                "candles_per_hour": get_candle_rate()
            },
            "tier2": {
                "status": "predicting",
                "model_loaded": is_model_loaded(),
                "avg_inference_ms": get_avg_inference_time()
            }
            # ... etc
        },
        "recent_errors": ERROR_BUFFER[-5:],
        "recent_activities": ACTIVITY_BUFFER[-10:]
    }
```

## Files to Create/Modify

1. **Create:** `src/api/routers/debug.py` - Debug endpoints
2. **Create:** `src/api/middleware/request_logger.py` - Request logging
3. **Create:** `src/core/error_tracker.py` - Error tracking
4. **Create:** `src/core/activity_tracker.py` - Activity logging
5. **Modify:** `main.py` - Add debug router and middleware
6. **Modify:** All routers - Add error tracking and activity logging

## Testing Checklist

After implementing:

- [ ] Visit `/api/debug/recent-errors` - Should return error list
- [ ] Visit `/api/debug/activity-log` - Should return activity stream
- [ ] Visit `/api/debug/component-status` - Should return component states
- [ ] Visit `/api/system/health/detailed` - Should return detailed health
- [ ] Trigger an error - Should appear in `/api/debug/recent-errors`
- [ ] Make API calls - Should appear in `/api/debug/recent-requests`
- [ ] Open dashboard - Activity log should update in real-time

## Benefits

1. **Visibility** - See exactly what's happening in the system
2. **Debugging** - Track errors with full context
3. **User Feedback** - Activity log shows system is working
4. **Proactive Monitoring** - Can check these endpoints automatically
5. **Performance** - Track slow endpoints and database queries

## Usage in Testing

After implementing, add to testing workflow:

```bash
# Check for recent errors
curl http://localhost:8100/api/debug/recent-errors

# Check component status
curl http://localhost:8100/api/debug/component-status

# Check activity log (what user sees)
curl http://localhost:8100/api/debug/activity-log
```

This gives immediate visibility into system health without relying on user feedback.
