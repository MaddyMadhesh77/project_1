import uuid
from types import SimpleNamespace

from app.services import graph as graph_module


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.execute_count = 0

    async def execute(self, *args, **kwargs):
        self.execute_count += 1
        return _FakeResult(self._rows)


def _row(parent: uuid.UUID, child: uuid.UUID):
    return SimpleNamespace(parent_version_id=parent, child_version_id=child)


def _reset_cache(monkeypatch, ttl: float = 60.0) -> None:
    monkeypatch.setattr(graph_module, "_cached_graph", None)
    monkeypatch.setattr(graph_module, "_cached_at", 0.0)
    monkeypatch.setattr(graph_module, "_CACHE_TTL_SECONDS", ttl)


async def test_load_graph_reuses_cache_within_ttl(monkeypatch):
    _reset_cache(monkeypatch)
    a, b = uuid.uuid4(), uuid.uuid4()
    db = _FakeSession([_row(a, b)])

    first = await graph_module.load_graph(db)
    second = await graph_module.load_graph(db)

    assert db.execute_count == 1  # second call served from cache, no DB round trip
    assert first is second
    assert b in graph_module.descendants(first, a)


async def test_load_graph_reloads_after_ttl_expires(monkeypatch):
    _reset_cache(monkeypatch, ttl=0.0)  # expires immediately
    a, b = uuid.uuid4(), uuid.uuid4()
    db = _FakeSession([_row(a, b)])

    await graph_module.load_graph(db)
    await graph_module.load_graph(db)

    assert db.execute_count == 2


async def test_invalidate_cache_forces_a_reload_on_next_call(monkeypatch):
    _reset_cache(monkeypatch)
    a, b = uuid.uuid4(), uuid.uuid4()
    db = _FakeSession([_row(a, b)])

    await graph_module.load_graph(db)
    graph_module.invalidate_cache()
    await graph_module.load_graph(db)

    assert db.execute_count == 2


async def test_record_edge_invalidates_the_cache(monkeypatch):
    _reset_cache(monkeypatch)
    a, b = uuid.uuid4(), uuid.uuid4()
    db = _FakeSession([_row(a, b)])

    await graph_module.load_graph(db)
    assert graph_module._cached_graph is not None

    await graph_module.record_edge(db, parent_version_id=a, child_version_id=b)

    assert graph_module._cached_graph is None
