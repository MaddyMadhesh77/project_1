from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, analytics, attack, chat, integrity, logs, memories, rollback, search, trust
from app.core.config import get_settings
from app.core.errors import UnhandledErrorMiddleware
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.security import require_api_key
from app.services.embedding import get_embedding_service


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

    # Interactive docs and the OpenAPI schema describe every route, including
    # the destructive ones -- public by default in FastAPI, and not behind
    # require_api_key. Only served in debug (local/demo) mode.
    docs = {} if settings.debug else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="RecoverMem API", version="0.1.0", lifespan=lifespan, **docs)

    # Order matters: the middleware added LAST is the outermost. CORS must wrap
    # everything that can produce a response on its own -- the rate limiter's
    # 429 and the catch-all's 500 -- or those go out without CORS headers and
    # the browser reports an opaque network error instead of the real status.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        api_key=settings.api_key,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Every data route lives under /v1, so a breaking API change doesn't
    # require changing frontend and backend in lockstep -- a future
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
        # POST /admin/reset -- truncates and re-seeds the whole
        # demo dataset. Just as destructive as attack.router's endpoints, so
        # it's gated the same way: never registered outside debug mode.
        v1.include_router(admin.router, dependencies=auth)
        # POST /trust/retrain rewrites model.pkl, which is then unpickled on
        # every scoring call -- never exposed outside debug mode.
        v1.include_router(trust.retrain_router, dependencies=auth)

    app.include_router(v1)

    return app


app = create_app()
