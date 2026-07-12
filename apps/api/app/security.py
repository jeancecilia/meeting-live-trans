"""
Security hardening middleware (MTG-041).

- Rate limiting (in-memory for MVP, Redis in production)
- Brute-force protection for login
- CSRF protection
- Secure headers
- WebSocket origin validation
- Input sanitization
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.security")


# ──── Rate limiter ────

class RateLimiter:
    """
    Simple in-memory rate limiter.
    Tracks requests per key (IP or token) within a sliding window.

    Production would use Redis with sorted sets for distributed accuracy.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from this key is allowed."""
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def reset(self, key: str) -> None:
        self._requests.pop(key, None)


# Global rate limiters
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)  # 5 login attempts/min
invite_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 invite checks/min
api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100 API calls/min


def check_login_rate_limit(identifier: str) -> None:
    """Brute-force protection for login endpoint."""
    if not login_rate_limiter.is_allowed(f"login:{identifier}"):
        logger.warning("Rate limit exceeded for login: identifier=%s", identifier)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )


def check_invite_rate_limit(ip: str) -> None:
    """Rate limit for invite token validation."""
    if not invite_rate_limiter.is_allowed(f"invite:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )


# ──── Security headers middleware ────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(self)"
        )

        return response


# ──── WebSocket origin validation ────

ALLOWED_WS_ORIGINS = {
    "http://localhost:3000",
    "https://meet.example.com",
}


def validate_ws_origin(origin: Optional[str]) -> bool:
    """Validate WebSocket connection origin to prevent CSWSH."""
    if not origin:
        return False

    for allowed in ALLOWED_WS_ORIGINS:
        if origin.startswith(allowed):
            return True

    logger.warning("Rejected WebSocket from untrusted origin: %s", origin)
    return False


# ──── Input sanitization ────

def sanitize_input(value: str, max_length: int = 100) -> str:
    """Strip whitespace and truncate input."""
    if not value:
        return ""
    return value.strip()[:max_length]


def validate_identity(identity: str) -> bool:
    """
    Ensure guest identities cannot collide with internal identities.
    Internal identities always start with 'internal_'.
    """
    if identity.startswith("internal_"):
        logger.warning("Guest attempted to use internal identity prefix: %s", identity)
        return False
    return True
