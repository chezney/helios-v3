"""
Rate limiting middleware for API protection.

Implements token bucket algorithm with per-IP rate limiting.
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, Tuple
import time


class RateLimiter(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket algorithm.

    Default: 100 requests per second per IP
    Tier-specific limits enforced via path checking
    """

    def __init__(self, app, requests_per_second: int = 100):
        super().__init__(app)
        self.requests_per_second = requests_per_second
        self.buckets: Dict[str, Tuple[float, float]] = defaultdict(lambda: (requests_per_second, time.time()))

        # Tier-specific limits
        self.tier_limits = {
            "/api/tier2/": 10,  # ML predictions: 10 req/sec
            "/api/trading/": 5,  # Trading operations: 5 req/sec
            "/api/market/": 50,  # Market data: 50 req/sec
        }

    async def dispatch(self, request: Request, call_next):
        """Process each request through rate limiter."""

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Determine rate limit for this path
        rate_limit = self.requests_per_second
        for path_prefix, limit in self.tier_limits.items():
            if request.url.path.startswith(path_prefix):
                rate_limit = limit
                break

        # Token bucket algorithm
        tokens, last_update = self.buckets[client_ip]
        now = time.time()
        elapsed = now - last_update

        # Refill tokens based on elapsed time
        tokens = min(rate_limit, tokens + elapsed * rate_limit)

        if tokens < 1:
            # Rate limit exceeded
            retry_after = int((1 - tokens) / rate_limit) + 1
            return HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": rate_limit,
                    "retry_after": retry_after
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after)
                }
            )

        # Consume one token
        tokens -= 1
        self.buckets[client_ip] = (tokens, now)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(int(tokens))

        return response

    def reset_bucket(self, ip: str):
        """Reset rate limit bucket for an IP (admin function)."""
        if ip in self.buckets:
            del self.buckets[ip]
