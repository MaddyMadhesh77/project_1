from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window request limiter, keyed by API key (if the caller sent
    one) else client IP -- /chat's embedding + LLM call + several DB writes
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
        exempt_paths: frozenset[str] = frozenset({"/health"}),
    ) -> None:
        super().__init__(app)
        self._limit = requests
        self._window = window_seconds
        self._exempt_paths = exempt_paths
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        hits = self._hits[key]
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
