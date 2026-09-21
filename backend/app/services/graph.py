from __future__ import annotations

import time
import uuid

import networkx as nx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DependencyEdge

# networkx.DiGraph wrapper over dependency_edges (DESIGN.md 6.9). Edges point
# parent -> child ("child was derived using parent as context"), so
# nx.descendants(graph, v) is exactly "everything transitively derived from
# v" -- reused as-is by the Phase 6 rollback engine's BFS step (6.10 step 1).

# Every chat turn (candidate retrieval -> record_edge) and every rollback
# call load_graph, which previously reloaded and rebuilt the whole
# dependency_edges table into a DiGraph from scratch on every single call,
# unbounded by table size. A short TTL cache keeps a burst of reads cheap;
# record_edge invalidates it immediately on write instead of waiting out the
# TTL, so a write is visible to the very next load_graph call. No caller
# mutates the returned graph, so handing back the same cached instance
# within the TTL window is safe. Process-local only -- multiple workers
# would each keep their own cache, consistent with this project's existing
# single-process deployment model (see embedding.py's model cache).
_CACHE_TTL_SECONDS = 5.0
_cached_graph: nx.DiGraph | None = None
_cached_at: float = 0.0


async def load_graph(db: AsyncSession, *, use_cache: bool = True) -> nx.DiGraph:
    """use_cache=False always reads the edges from this session. Rollback
    needs that: record_edge invalidates the cache before its transaction
    commits, so a concurrent reload can cache a graph missing a just-written
    edge for up to the TTL -- and a rollback using it would miss a memory
    just derived from the poison. Display-only callers can use the cache."""
    global _cached_graph, _cached_at

    now = time.monotonic()
    if use_cache and _cached_graph is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_graph

    rows = (await db.execute(sa.select(DependencyEdge.parent_version_id, DependencyEdge.child_version_id))).all()
    graph = nx.DiGraph()
    graph.add_edges_from((row.parent_version_id, row.child_version_id) for row in rows)

    _cached_graph = graph
    _cached_at = now
    return graph


def invalidate_cache() -> None:
    global _cached_graph, _cached_at
    _cached_graph = None
    _cached_at = 0.0


def descendants(graph: nx.DiGraph, version_id: uuid.UUID) -> set[uuid.UUID]:
    if version_id not in graph:
        return set()
    return nx.descendants(graph, version_id)


def ancestors(graph: nx.DiGraph, version_id: uuid.UUID) -> set[uuid.UUID]:
    if version_id not in graph:
        return set()
    return nx.ancestors(graph, version_id)


async def record_edge(
    db: AsyncSession,
    *,
    parent_version_id: uuid.UUID,
    child_version_id: uuid.UUID,
    relation_type: str = "derived_from",
) -> None:
    """Write a dependency_edges row. Idempotent (ON CONFLICT DO NOTHING against
    the (parent_version_id, child_version_id) unique constraint) so repeated
    calls -- e.g. re-running scripts/seed_demo.py, or a chat turn retrieving
    the same context memory twice -- don't raise or duplicate edges.
    """
    if parent_version_id == child_version_id:
        return
    stmt = (
        pg_insert(DependencyEdge)
        .values(parent_version_id=parent_version_id, child_version_id=child_version_id, relation_type=relation_type)
        .on_conflict_do_nothing(index_elements=["parent_version_id", "child_version_id"])
    )
    await db.execute(stmt)
    invalidate_cache()


async def carry_forward_edges(db: AsyncSession, *, old_version_id: uuid.UUID, new_version_id: uuid.UUID) -> None:
    """When a memory is versioned (an update, not a brand-new memory),
    existing dependency_edges rows still reference the old version_id on
    whichever side it was on -- so a dependent's ancestor traversal (or the
    updated memory's own descendant traversal) silently stops seeing the
    relationship once `memories.current_version_id` moves past it. This was
    bug #7: "if memory B was derived from A, and A gets updated, B's graph
    edges still point to the old version." Mirrors each edge touching
    old_version_id onto new_version_id without touching the original edges
    (dependency_edges is append-only, like every other table here).
    """
    rows = (
        await db.execute(
            sa.select(DependencyEdge).where(
                sa.or_(
                    DependencyEdge.parent_version_id == old_version_id,
                    DependencyEdge.child_version_id == old_version_id,
                )
            )
        )
    ).scalars().all()

    for edge in rows:
        parent = new_version_id if edge.parent_version_id == old_version_id else edge.parent_version_id
        child = new_version_id if edge.child_version_id == old_version_id else edge.child_version_id
        await record_edge(db, parent_version_id=parent, child_version_id=child, relation_type=edge.relation_type)
