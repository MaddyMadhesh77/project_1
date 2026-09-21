from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import networkx as nx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Memory, MemoryVersion, RollbackEvent, RollbackOutcome, TrustEvent
from app.services import graph as graph_service
from app.services import merkle, versioning
from app.services.features import FeatureVector
from app.services.trust_engine import TrustResult, score_candidate

# Dependency-aware rollback / recovery (DESIGN.md 6.10). Triggered on a
# version believed poisoned; walks the dependency graph, re-validates every
# descendant with that version's influence excluded, and either keeps,
# reverts, or removes each one depending on whether it still has independent
# support. Every outcome -- including the poisoned version's own -- is
# written as a *new* version (never a mutation), matching the versioning
# model everywhere else in this codebase (6.6), so the Merkle root always
# changes after a rollback and the full history stays walkable.

OUTCOME_KEPT = "kept"
OUTCOME_REVERTED = "reverted"
OUTCOME_REMOVED = "removed"
# Not touched: a newer version of the memory already replaced this one. Used
# for the poisoned version itself when it was already superseded (its newer
# state is left in place while its descendants are still recovered), and for
# stale versions of descendants. Carries no safe/poisoned verdict for training.
OUTCOME_SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ParentRef:
    version_id: uuid.UUID
    memory_id: uuid.UUID
    version_number: int


def valid_sources(
    parents: list[ParentRef], poisoned_version_id: uuid.UUID, removed_memory_ids: set[uuid.UUID]
) -> list[ParentRef]:
    """The parent memories that still independently support a node.

    Support is judged per parent *memory*, not per parent version: when a
    memory is updated, carry_forward_edges copies its outgoing edges onto the
    new version, so a child ends up with edges from several versions of the
    same memory. Retrieval only ever sees a memory's current version, so the
    child was really derived from exactly one of them -- the earliest one it
    has an edge from; the later edges are copies. That source is invalid if
    it is the poisoned version, or if its memory was removed earlier in this
    rollback run (a reverted memory still counts -- it survived, with
    different content).

    Without this, a copy of the poisoned edge on a newer version of the same
    memory counted as "independent" support and kept the very children
    derived from the poison -- and a removed memory's older versions still
    counted as support.
    """
    sources: dict[uuid.UUID, ParentRef] = {}
    for parent in parents:
        current = sources.get(parent.memory_id)
        if current is None or parent.version_number < current.version_number:
            sources[parent.memory_id] = parent
    return [
        source
        for source in sources.values()
        if source.version_id != poisoned_version_id and source.memory_id not in removed_memory_ids
    ]


def classify_outcome(*, has_independent_support: bool, has_prior_version: bool) -> str:
    """The 3-way branch from DESIGN.md 6.10 step 3, isolated as a pure
    function so the decision logic itself -- independent of any DB/graph
    plumbing -- is directly unit-testable."""
    if has_independent_support:
        return OUTCOME_KEPT
    if has_prior_version:
        return OUTCOME_REVERTED
    return OUTCOME_REMOVED


def processing_order(dep_graph: nx.DiGraph, poisoned_version_id: uuid.UUID, descendant_ids: set[uuid.UUID]) -> list[uuid.UUID]:
    """Topological order over {poisoned_version_id} ∪ descendants, poisoned
    version first. Processing in this order is what lets a downstream node's
    "does it still have independent support" check see upstream nodes'
    already-decided outcomes for this same rollback run (see valid_sources) --
    e.g. if B is removed and C solely depended on B, C must lose B as valid
    support too, not just the original poisoned root.
    """
    nodes = {poisoned_version_id, *descendant_ids}
    order = list(nx.topological_sort(dep_graph.subgraph(nodes)))
    # nodes with no edges among this set (shouldn't happen for real
    # descendants, but keep this total) still need to appear somewhere.
    missing = nodes - set(order)
    return order + list(missing)


def _cosine(a: list[float], b: list[float]) -> float:
    # Embeddings are stored pre-normalized (EmbeddingService uses
    # normalize_embeddings=True), so a plain dot product is cosine similarity.
    return sum(x * y for x, y in zip(a, b))


@dataclass
class NodeOutcome:
    version_id: uuid.UUID
    memory_id: uuid.UUID
    text: str
    outcome: str  # kept | reverted | removed
    new_version_id: uuid.UUID
    trust_score: float
    reason: str


@dataclass
class RollbackResult:
    rollback_id: uuid.UUID
    root_version_id: uuid.UUID
    affected: list[NodeOutcome]
    triggered_by: str
    started_at: datetime
    completed_at: datetime
    merkle_root: str


async def _clean_prior_version(
    db: AsyncSession, version: MemoryVersion, tainted_version_ids: set[uuid.UUID]
) -> MemoryVersion | None:
    """The latest earlier version of this memory that is neither the poisoned
    version nor derived from it. Reverting to the immediately previous
    version isn't enough: a memory created from the poison carries its
    dependency edges onto every later version, so its older versions are just
    as tainted, and reverting to one would restore poison-derived content."""
    result = await db.execute(
        sa.select(MemoryVersion)
        .where(
            MemoryVersion.memory_id == version.memory_id,
            MemoryVersion.version_number < version.version_number,
            MemoryVersion.version_id.not_in(tainted_version_ids) if tainted_version_ids else sa.true(),
        )
        .order_by(MemoryVersion.version_number.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _process_node(
    db: AsyncSession,
    *,
    version_id: uuid.UUID,
    is_root: bool,
    dep_graph: nx.DiGraph,
    outcomes: dict[uuid.UUID, NodeOutcome],
    poisoned_version_id: uuid.UUID,
    tainted_version_ids: set[uuid.UUID],
    settings: Settings,
    rollback_marker: str,
) -> NodeOutcome:
    # populate_existing: decide from committed state, not this session's cache.
    version = await db.get(MemoryVersion, version_id, populate_existing=True)
    memory = await db.get(Memory, version.memory_id, populate_existing=True)

    # Only the current version of a memory reflects what's actually believed
    # right now. A stale version -- including the poisoned version itself, if
    # it was already replaced -- is never rewritten: writing onto its memory
    # would revert past (and destroy) the newer state. Its descendants are
    # still processed; their own current versions carry the dependency
    # forward via carry_forward_edges.
    if memory.current_version_id != version_id:
        current = await db.get(MemoryVersion, memory.current_version_id)
        reason = (
            f"poisoned version already superseded by version {current.version_number}; newer state left in place"
            if is_root
            else f"already superseded by version {current.version_number} -- not touched"
        )
        return NodeOutcome(
            version_id=version_id,
            memory_id=memory.memory_id,
            text=version.text,
            outcome=OUTCOME_SUPERSEDED,
            new_version_id=memory.current_version_id,
            trust_score=float(version.trust_score),
            reason=reason,
        )

    # Already removed by an earlier rollback (e.g. the same rollback
    # triggered twice): there's nothing left to undo. Re-processing it would
    # just write another identical "removed" version.
    if not is_root and memory.status == "rolled_back":
        return NodeOutcome(
            version_id=version_id,
            memory_id=memory.memory_id,
            text=version.text,
            outcome=OUTCOME_REMOVED,
            new_version_id=version_id,
            trust_score=float(version.trust_score),
            reason="already removed by an earlier rollback -- not rewritten",
        )

    valid_parents: list[ParentRef] = []
    if is_root:
        has_independent_support = False  # the root IS the poison; never "kept"
    else:
        parents = []
        for parent_id in dep_graph.predecessors(version_id):
            parent = await db.get(MemoryVersion, parent_id)
            parents.append(ParentRef(parent.version_id, parent.memory_id, parent.version_number))
        removed_memory_ids = {o.memory_id for o in outcomes.values() if o.outcome == OUTCOME_REMOVED}
        valid_parents = valid_sources(parents, poisoned_version_id, removed_memory_ids)
        has_independent_support = len(valid_parents) > 0

    prior = await _clean_prior_version(db, version, tainted_version_ids)
    outcome_kind = classify_outcome(has_independent_support=has_independent_support, has_prior_version=prior is not None)

    trust_result: TrustResult | None = None
    provenance_fields = {
        "conversation_id": uuid.uuid4(),
        "source_type": "admin_override",
        "model_version": None,
        "created_by": rollback_marker,
        "raw_input": None,
    }

    if outcome_kind == OUTCOME_KEPT:
        valid_parent_versions = [await db.get(MemoryVersion, p.version_id) for p in valid_parents]
        best_parent = max(valid_parent_versions, key=lambda p: float(p.trust_score))
        features = FeatureVector(
            similarity=_cosine(list(version.embedding), list(best_parent.embedding)),
            contradiction=0.0,
            source_reliability=1.0,
            memory_age_days=float((datetime.now(timezone.utc) - memory.created_at).days),
            prior_trust_score=float(best_parent.trust_score),
            corroboration_count=max(0, len(valid_parent_versions) - 1),
            conversation_recency=1.0,
            has_match=True,
        )
        provenance_fields["raw_input"] = (
            f"re-validated after rollback of {poisoned_version_id}: still independently corroborated"
        )
        text, embedding = version.text, list(version.embedding)
        reason = f"still corroborated by {len(valid_parent_versions)} independent parent(s)"
    elif outcome_kind == OUTCOME_REVERTED:
        features = FeatureVector(
            similarity=0.0,
            contradiction=0.0,
            source_reliability=1.0,
            memory_age_days=0.0,
            prior_trust_score=0.0,
            corroboration_count=0,
            conversation_recency=1.0,
            has_match=False,
        )
        provenance_fields["raw_input"] = (
            f"reverted to version {prior.version_number} after rollback of poisoned version {poisoned_version_id}"
        )
        text, embedding = prior.text, list(prior.embedding)
        reason = f'solely dependent on the poisoned version; reverted to version {prior.version_number} ("{prior.text}")'
    else:
        # No trust_engine call here: there's nothing left to score against --
        # no independent support and no prior state to fall back on -- so
        # this is unconditionally rejected rather than scored.
        features = FeatureVector(
            similarity=0.0,
            contradiction=1.0,
            source_reliability=0.0,
            memory_age_days=0.0,
            prior_trust_score=0.0,
            corroboration_count=0,
            conversation_recency=1.0,
            has_match=False,
        )
        provenance_fields["raw_input"] = (
            f"removed after rollback of poisoned version {poisoned_version_id}: no independent support, no prior version"
        )
        text, embedding = version.text, list(version.embedding)
        reason = "solely dependent on the poisoned version; no prior version to revert to"
        trust_result = TrustResult(score=0.0, breakdown={"rollback_removed": -100.0}, decision="reject")

    if outcome_kind != OUTCOME_REMOVED:
        trust_result = score_candidate(features, settings)

    assert trust_result is not None

    new_version = await versioning.write_version(
        db,
        memory_id=memory.memory_id,
        text=text,
        embedding=embedding,
        trust_score=trust_result.score,
        trust_breakdown=trust_result.breakdown,
        decision=trust_result.decision,
        provenance_fields=provenance_fields,
        # STATUS_BY_DECISION would otherwise mark a removed memory
        # "quarantined" -- same bucket a fresh contradicted chat statement
        # lands in. "rolled_back" is the status DESIGN.md 5 reserves for a
        # memory purged as a consequence of an *ancestor's* rollback. Passed
        # into the write itself: setting it afterwards (after a db.refresh
        # that discarded write_version's own pending changes) only stuck
        # thanks to an incidental autoflush.
        status="rolled_back" if outcome_kind == OUTCOME_REMOVED else None,
        # Refuse to overwrite a concurrent update made after the check above.
        expected_current_version_id=version_id,
    )

    db.add(
        TrustEvent(
            version_id=new_version.version_id,
            event_type="rolled_back",
            trust_score=trust_result.score,
            details={"breakdown": trust_result.breakdown, "features": vars(features), "rollback_outcome": outcome_kind},
        )
    )

    return NodeOutcome(
        version_id=version_id,
        memory_id=memory.memory_id,
        # The affected version's own content (matching version_id), not the
        # post-rollback content: a reverted node used to read "preference:
        # Python -> Reverted", hiding what was actually undone. The restored
        # content is named in `reason`.
        text=version.text,
        outcome=outcome_kind,
        new_version_id=new_version.version_id,
        trust_score=trust_result.score,
        reason=reason,
    )


# Arbitrary constant key for pg_advisory_xact_lock.
_ROLLBACK_LOCK_KEY = 0x524F4C4C  # "ROLL"


async def run_rollback(db: AsyncSession, *, poisoned_version_id: uuid.UUID, triggered_by: str, settings: Settings) -> RollbackResult:
    # One rollback at a time, held until this transaction ends. Two
    # concurrent rollbacks (a double-click, two tabs) used to both act on the
    # same pre-rollback state; now the second waits and then sees the first's
    # result -- e.g. its target already superseded. Rollbacks are rare admin
    # actions, so serializing them costs nothing and avoids lock-ordering
    # deadlocks between overlapping dependency chains.
    await db.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ROLLBACK_LOCK_KEY})
    started_at = datetime.now(timezone.utc)

    poisoned_version = await db.get(MemoryVersion, poisoned_version_id, populate_existing=True)
    if poisoned_version is None:
        raise ValueError(f"version {poisoned_version_id} not found")

    # Always fresh, never the TTL cache: a stale graph would silently miss
    # descendants of the poison (see load_graph).
    dep_graph = await graph_service.load_graph(db, use_cache=False)
    descendant_ids = graph_service.descendants(dep_graph, poisoned_version_id)
    order = processing_order(dep_graph, poisoned_version_id, descendant_ids)

    outcomes: dict[uuid.UUID, NodeOutcome] = {}
    affected: list[NodeOutcome] = []
    for version_id in order:
        outcome = await _process_node(
            db,
            version_id=version_id,
            is_root=(version_id == poisoned_version_id),
            dep_graph=dep_graph,
            outcomes=outcomes,
            poisoned_version_id=poisoned_version_id,
            tainted_version_ids={poisoned_version_id, *descendant_ids},
            settings=settings,
            rollback_marker="rollback_engine",
        )
        outcomes[version_id] = outcome
        affected.append(outcome)

    completed_at = datetime.now(timezone.utc)

    # One recompute for the whole rollback, not one per node -- write_version
    # no longer does this itself (see services/versioning.py) precisely
    # because a multi-node dependency chain here used to pay for a full
    # O(active leaves) tree rebuild on every single node it touched.
    new_root = await merkle.compute_and_store_root(db)

    event = RollbackEvent(
        root_version_id=poisoned_version_id,
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=completed_at,
        merkle_root_hash=new_root.root_hash,
    )
    db.add(event)
    await db.flush()  # need event.rollback_id for the outcome rows below

    for index, o in enumerate(affected):
        db.add(
            RollbackOutcome(
                rollback_id=event.rollback_id,
                outcome_index=index,
                memory_id=o.memory_id,
                version_id=o.version_id,
                text=o.text,
                outcome=o.outcome,
                new_version_id=o.new_version_id,
                trust_score=o.trust_score,
                reason=o.reason,
            )
        )
    await db.flush()

    return RollbackResult(
        rollback_id=event.rollback_id,
        root_version_id=poisoned_version_id,
        affected=affected,
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=completed_at,
        merkle_root=new_root.root_hash,
    )
