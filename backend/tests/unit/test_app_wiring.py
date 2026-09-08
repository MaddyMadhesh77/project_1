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
