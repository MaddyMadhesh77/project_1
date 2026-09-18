"""DB-backed integration test fixtures.

Runs against a real Postgres + pgvector -- the same docker-compose service
the app uses, but a separate `<db>_test` database (override with
TEST_DATABASE_URL). The database is created if missing and migrated to
`alembic upgrade head` once per session; every test then starts from empty
tables (TRUNCATE, like POST /admin/reset), so tests can commit freely the way
the real routes do.

If Postgres isn't reachable, every integration test is skipped (not failed)
so the unit suite still runs anywhere. Set REQUIRE_DB=1 (e.g. in CI) to make
an unreachable database a hard failure instead.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.routes.admin import _TABLES
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
from app.services import graph

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _test_database_url() -> URL:
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return make_url(override)
    base = make_url(get_settings().database_url)
    return base.set(database=f"{base.database}_test")


async def _ensure_database(url: URL) -> None:
    conn = await asyncpg.connect(
        host=url.host, port=url.port, user=url.username, password=url.password, database="postgres"
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    try:
        asyncio.run(_ensure_database(url))
    except (OSError, asyncpg.PostgresError) as exc:
        message = (
            f"Postgres not reachable at {url.host}:{url.port} ({exc.__class__.__name__}: {exc}). "
            "Start it with `docker compose up -d` from the repo root."
        )
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(message)
        pytest.skip(message)

    url_str = url.render_as_string(hide_password=False)
    # alembic/env.py reads the URL from Settings, i.e. from DATABASE_URL.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url_str},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed against the test database:\n{result.stderr}")
    return url_str


@pytest.fixture
def settings() -> Settings:
    # Pinned rather than read from the local .env: rule-engine scoring only
    # (deterministic regardless of whether a model.pkl exists), the templated
    # LLM client (no network), demo/debug routes registered, no API key.
    return Settings(ml_bootstrap_on_synthetic=False, anthropic_api_key=None, debug=True, api_key=None)


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    graph.invalidate_cache()
    yield engine
    graph.invalidate_cache()
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
