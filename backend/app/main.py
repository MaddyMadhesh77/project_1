import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin, analytics, attack, chat, integrity, logs, memories, rollback, search, trust
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.security import require_api_key
from app.services.embedding import get_embedding_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_embedding_service()  # warm the model once at startup, not on the first chat request
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    if not settings.debug and not settings.api_key:
        # debug=False means "reachable by more than just the operator" --
        # refuse to boot wide open rather than silently serving every
        # endpoint, including the destructive attack/rollback routes,
        # unauthenticated. debug=True (local/demo default) tolerates this,
        # with a per-process warning logged from require_api_key instead.
        raise RuntimeError(
            "DEBUG=false requires API_KEY to be set -- refusing to start unauthenticated in "
            "a non-debug deployment. Set API_KEY, or DEBUG=true for local/demo use."
        )

    app = FastAPI(title="RecoverMem API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # bugs.md #14: an uncaught exception previously propagated straight to
        # the client. Log the full traceback server-side (exc_info via
        # .exception) and return a flat, generic JSON body -- never str(exc),
        # which can echo internal details (a raw SQL error, a file path, a
        # stack frame) back to whoever sent the request.
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Every data route lives under /v1 (bugs.md #13: "any breaking change
    # requires coordinating frontend and backend simultaneously") -- a future
    # v2 can be introduced alongside this one instead of forcing a
    # synchronized cutover. /health stays unprefixed: it's an infra liveness
    # probe, not a versioned data API.
    auth = [Depends(require_api_key)]
    v1 = APIRouter(prefix="/v1")
    v1.include_router(chat.router, dependencies=auth)
    v1.include_router(memories.router, dependencies=auth)
    v1.include_router(trust.router, dependencies=auth)
    v1.include_router(integrity.router, dependencies=auth)
    v1.include_router(rollback.router, dependencies=auth)
    v1.include_router(analytics.router, dependencies=auth)
    v1.include_router(logs.router, dependencies=auth)
    v1.include_router(search.router, dependencies=auth)

    if settings.debug:
        # Raw-SQL-mutation attack-simulator endpoints (tamper-db,
        # inject-poison) -- demo-only. Not even registered outside debug mode,
        # so a production deployment has no route to hit regardless of
        # auth/rate-limit config.
        v1.include_router(attack.router, dependencies=auth)
        # POST /admin/reset (bugs.md #11) -- truncates and re-seeds the whole
        # demo dataset. Just as destructive as attack.router's endpoints, so
        # it's gated the same way: never registered outside debug mode.
        v1.include_router(admin.router, dependencies=auth)

    app.include_router(v1)

    return app


app = create_app()
