from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimitMiddleware


def _client(requests: int = 2, window_seconds: int = 60) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.add_middleware(RateLimitMiddleware, requests=requests, window_seconds=window_seconds)
    return TestClient(app)


def test_allows_requests_under_the_limit():
    client = _client(requests=2)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200


def test_blocks_requests_over_the_limit():
    client = _client(requests=2)
    client.get("/ping")
    client.get("/ping")
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_health_endpoint_is_exempt():
    client = _client(requests=1)
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_budget_is_tracked_per_client_key_not_globally():
    client = _client(requests=1)
    assert client.get("/ping", headers={"X-API-Key": "a"}).status_code == 200
    assert client.get("/ping", headers={"X-API-Key": "b"}).status_code == 200
    assert client.get("/ping", headers={"X-API-Key": "a"}).status_code == 429
