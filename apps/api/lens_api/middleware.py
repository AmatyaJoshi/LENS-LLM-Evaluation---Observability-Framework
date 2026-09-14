"""Request guards (SPEC.md §1.2 single-org hardening).

- Body size cap: reject payloads over ``max_request_bytes`` with 413 before they are
  buffered, protecting the ingest path from oversized OTLP posts.
- Token-bucket rate limit: per API key (or client IP) requests-per-minute, ``0`` disables.
  In-memory and per-process — fine for a single-node deployment; front with a shared
  limiter (e.g. Redis) for multi-node.
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(
                {"detail": f"request body exceeds {self.max_bytes} bytes"}, status_code=413
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window-ish token bucket keyed by API key, falling back to client IP."""

    def __init__(self, app: ASGIApp, rpm: int) -> None:
        super().__init__(app)
        self.rpm = rpm
        self.capacity = float(rpm)
        self.refill_per_sec = rpm / 60.0
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (self.capacity, time.monotonic())
        )

    def _key(self, request: Request) -> str:
        k = request.headers.get("x-lens-api-key") or request.headers.get("authorization")
        if k:
            return k
        return request.client.host if request.client else "anon"

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path == "/health":
            return await call_next(request)
        key = self._key(request)
        tokens, last = self._buckets[key]
        now = time.monotonic()
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_sec)
        if tokens < 1.0:
            retry = max(1, int((1.0 - tokens) / self.refill_per_sec))
            self._buckets[key] = (tokens, now)
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        self._buckets[key] = (tokens - 1.0, now)
        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        return response
