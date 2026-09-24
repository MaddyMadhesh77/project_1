from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimitMiddleware


def _client(requests: int = 2, window_seconds: int = 60, api_key: str | None = None) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.add_middleware(RateLimitMiddleware, requests=requests, window_seconds=window_seconds, api_key=api_key)
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


def test_arbitrary_api_key_values_share_the_ip_budget():
    # Regression (audit A8): every distinct X-API-Key value used to get its
    # own fresh budget, so rotating a random header bypassed the limit.
    client = _client(requests=1, api_key="secret")
    assert client.get("/ping", headers={"X-API-Key": "a"}).status_code == 200
    assert client.get("/ping", headers={"X-API-Key": "b"}).status_code == 429
    assert client.get("/ping").status_code == 429


def test_valid_api_key_gets_its_own_budget():
    client = _client(requests=1, api_key="secret")
    assert client.get("/ping").status_code == 200
    assert client.get("/ping", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/ping", headers={"X-API-Key": "secret"}).status_code == 429


def test_idle_clients_are_swept(monkeypatch):
    from app.core import rate_limit

    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    middleware = RateLimitMiddleware(app=lambda *a: None, requests=5, window_seconds=60)
    middleware._hits = {f"ip:10.0.0.{i}": rate_limit.deque([now[0]]) for i in range(100)}

    now[0] += 61
    middleware._sweep(now[0])

    assert middleware._hits == {}
