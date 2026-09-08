from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.security import require_api_key


def _client(settings: Settings) -> TestClient:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected() -> dict:
        return {"ok": True}

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_open_when_no_api_key_configured():
    # Today's zero-config local/demo behavior: unset api_key doesn't lock
    # anyone out (see require_api_key's debug=True tolerance).
    resp = _client(Settings(api_key=None)).get("/protected")
    assert resp.status_code == 200


def test_rejects_request_with_no_key_when_configured():
    resp = _client(Settings(api_key="secret")).get("/protected")
    assert resp.status_code == 401


def test_rejects_wrong_key_when_configured():
    resp = _client(Settings(api_key="secret")).get("/protected", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_accepts_correct_key_when_configured():
    resp = _client(Settings(api_key="secret")).get("/protected", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200
