from __future__ import annotations

import hmac
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window request limiter, keyed by API key (only if the caller
    sent the *valid* one) else client IP -- /chat's embedding + LLM call + several DB writes
    per request is the expensive path this is mainly protecting, but every
    route (other than /health) is bounded the same way rather than trying to
    price each endpoint individually.

    In-process, single-worker only: state is a plain dict, not a shared
    store. Fine for this project's single-uvicorn-process deployment model --
    running multiple workers/instances would need a shared backend (e.g.
    Redis) instead, since each process would otherwise enforce its own
    independent budget.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: int,
        api_key: str | None = None,
        exempt_paths: frozenset[str] = frozenset({"/health"}),
    ) -> None:
        super().__init__(app)
        self._limit = requests
        self._window = window_seconds
        self._api_key = api_key
        self._exempt_paths = exempt_paths
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = time.monotonic()

    def _client_key(self, request: Request) -> str:
        # Only the configured key gets its own bucket. Trusting any
        # X-API-Key value let an unauthenticated client mint a fresh budget
        # per random header value (and grow _hits without bound); anything
        # else -- missing, wrong, or no key configured -- is limited by IP.
        sent = request.headers.get("x-api-key")
        if self._api_key and sent and hmac.compare_digest(sent.encode(), self._api_key.encode()):
            return "key"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    def _sweep(self, now: float) -> None:
        """Drop clients with no hits inside the window, at most once per
        window, so a stream of one-off clients (e.g. rotating IPs) can't grow
        _hits forever."""
        if now - self._last_sweep < self._window:
            return
        cutoff = now - self._window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] < cutoff]:
            del self._hits[key]
        self._last_sweep = now

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_after = max(1, int(self._window - (now - hits[0])))
            return JSONResponse(
                {"detail": "rate limit exceeded, try again later"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
