from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, memories, trust
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.embedding import get_embedding_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_embedding_service()  # warm the model once at startup, not on the first chat request
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="RecoverMem API", version="0.1.0", lifespan=lifespan)

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

    app.include_router(chat.router)
    app.include_router(memories.router)
    app.include_router(trust.router)

    return app


app = create_app()
