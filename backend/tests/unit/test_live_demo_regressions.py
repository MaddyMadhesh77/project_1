"""Regression guards for live-demo failures that need no real database."""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app


def test_chat_returns_503_when_the_database_is_unreachable():
    # Previously the per-candidate `except Exception` swallowed the connection
    # error and returned 200 with an empty stored_memories list.
    dead_engine = create_async_engine("postgresql+asyncpg://x:x@127.0.0.1:1/x", poolclass=NullPool)
    sessions = async_sessionmaker(dead_engine)

    async def _dead_db() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _dead_db
    app.dependency_overrides[get_settings] = lambda: Settings(anthropic_api_key=None, api_key=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/v1/chat", json={"message": "I live in Bangalore", "history": []})

    assert response.status_code == 503
    assert response.json() == {"detail": "memory store unavailable"}


def test_rate_limited_response_still_carries_cors_headers(monkeypatch):
    # The rate limiter used to wrap CORS, so a 429 had no
    # Access-Control-Allow-Origin and the browser saw an opaque network error.
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        origin = get_settings().cors_origin_list[0]
        statuses = [client.get("/v1/trust/model", headers={"Origin": origin}) for _ in range(2)]
    finally:
        get_settings.cache_clear()

    assert statuses[-1].status_code == 429
    assert statuses[-1].headers.get("access-control-allow-origin") == origin


def test_chat_history_cap_is_fifty_messages():
    # The frontend trims to this same number (Chat.tsx MAX_HISTORY); if the
    # backend cap changes, that constant must change with it.
    from app.api.routes.chat import ChatRequest

    assert ChatRequest.model_fields["history"].metadata[0].max_length == 50
