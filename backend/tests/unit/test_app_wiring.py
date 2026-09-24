import os

import pytest

from app.core.config import get_settings


def _fresh_app(**env: str):
    for key in ("DEBUG", "API_KEY"):
        os.environ.pop(key, None)
    os.environ.update(env)
    get_settings.cache_clear()
    try:
        from app.main import create_app

        return create_app()
    finally:
        for key in ("DEBUG", "API_KEY"):
            os.environ.pop(key, None)
        get_settings.cache_clear()


def test_debug_mode_registers_attack_router():
    app = _fresh_app(DEBUG="true")
    paths = app.openapi()["paths"]
    assert any(path.startswith("/v1/attack") for path in paths)


def test_non_debug_mode_does_not_register_attack_router():
    app = _fresh_app(DEBUG="false", API_KEY="secret")
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/v1/attack") for path in paths)


def test_non_debug_mode_without_api_key_refuses_to_start():
    with pytest.raises(RuntimeError):
        _fresh_app(DEBUG="false")


def test_health_route_has_no_auth_dependency():
    app = _fresh_app(DEBUG="false", API_KEY="secret")
    health_route = next(route for route in app.routes if getattr(route, "path", None) == "/health")
    assert health_route.dependant.dependencies == []


def test_api_docs_are_not_served_outside_debug_mode():
    # Regression (audit A10): /docs, /redoc and /openapi.json were public in
    # production, describing every route without requiring the API key.
    from fastapi.testclient import TestClient

    prod = TestClient(_fresh_app(DEBUG="false", API_KEY="secret"))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod.get(path).status_code == 404
    assert TestClient(_fresh_app(DEBUG="true")).get("/openapi.json").status_code == 200


def test_retrain_endpoint_only_registered_in_debug_mode():
    # Regression (audit A9): retrain rewrites model.pkl, which every scoring
    # call then unpickles -- it was registered unconditionally.
    assert "/v1/trust/retrain" in _fresh_app(DEBUG="true").openapi()["paths"]
    prod_paths = _fresh_app(DEBUG="false", API_KEY="secret").openapi()["paths"]
    assert "/v1/trust/retrain" not in prod_paths
    assert "/v1/trust/model" in prod_paths


def test_unhandled_error_returns_generic_500_with_cors_headers():
    # The catch-all used to run outside CORS, so a 500 reached the browser as
    # an opaque network error.
    from fastapi.testclient import TestClient

    app = _fresh_app(DEBUG="true")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    origin = get_settings().cors_origin_list[0]
    response = TestClient(app, raise_server_exceptions=False).get("/boom", headers={"Origin": origin})

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert response.headers.get("access-control-allow-origin") == origin


def test_search_rejects_empty_or_blank_queries_and_out_of_range_params():
    # Regression (audit A11/B23): q="" was embedded and returned arbitrary
    # neighbours; out-of-range limits were silently clamped.
    from fastapi.testclient import TestClient

    client = TestClient(_fresh_app(DEBUG="true"))
    assert client.get("/v1/search", params={"q": ""}).status_code == 422
    assert client.get("/v1/search", params={"q": "   "}).status_code == 422
    assert client.get("/v1/search", params={"q": "python", "top_k": 0}).status_code == 422
    assert client.get("/v1/logs", params={"limit": 500}).status_code == 422
    assert client.get("/v1/memories", params={"offset": -1}).status_code == 422


def test_param_bounds_are_published_in_the_schema():
    params = {
        p["name"]: p["schema"]
        for p in _fresh_app(DEBUG="true").openapi()["paths"]["/v1/logs"]["get"]["parameters"]
    }
    assert params["limit"]["maximum"] == 200
    assert params["offset"]["minimum"] == 0


def test_chat_rejects_empty_or_blank_messages():
    from fastapi.testclient import TestClient

    client = TestClient(_fresh_app(DEBUG="true"))
    assert client.post("/v1/chat", json={"message": "", "history": []}).status_code == 422
    assert client.post("/v1/chat", json={"message": "  \n ", "history": []}).status_code == 422


def test_inject_poison_validates_text_and_score():
    # Score 5000 used to overflow the NUMERIC(5,2) column (500); negative
    # scores and empty text were stored as-is.
    from fastapi.testclient import TestClient

    client = TestClient(_fresh_app(DEBUG="true"))
    for body in (
        {"text": "goal: x", "forced_trust_score": 5000},
        {"text": "goal: x", "forced_trust_score": -1},
        {"text": "", "forced_trust_score": 90},
        {"text": "   ", "forced_trust_score": 90},
    ):
        assert client.post("/v1/attack/inject-poison", json=body).status_code == 422, body
