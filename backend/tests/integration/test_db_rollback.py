"""Dependency-aware rollback's DB path: keep / revert / remove, plus the
audit records and integrity state it leaves behind."""
from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from factories import write

from app.models import Memory, MemoryVersion, RollbackEvent, RollbackOutcome
from app.services import demo_seed, graph, merkle
from app.services.rollback import run_rollback


async def _current_text(db, memory_id) -> str:
    memory = await db.get(Memory, memory_id)
    return (await db.get(MemoryVersion, memory.current_version_id)).text


async def test_demo_chain_rollback_removes_every_dependent_memory(db, settings):
    await demo_seed.seed_demo(db, settings)
    await db.commit()
    root = (
        await db.execute(sa.select(MemoryVersion).where(MemoryVersion.text == "preference: Python"))
    ).scalar_one()

    result = await run_rollback(db, poisoned_version_id=root.version_id, triggered_by="test", settings=settings)
    await db.commit()

    assert [o.outcome for o in result.affected] == ["removed", "removed", "removed"]
    statuses = (await db.execute(sa.select(Memory.status))).scalars().all()
    assert statuses == ["rolled_back"] * 3
    assert (await db.execute(sa.select(sa.func.count()).select_from(RollbackEvent))).scalar_one() == 1
    assert (await db.execute(sa.select(sa.func.count()).select_from(RollbackOutcome))).scalar_one() == 3
    # Regression (Phase 8): verify used to report tampering right after a clean rollback.
    assert not (await merkle.verify_integrity(db)).tampered


async def test_rollback_reverts_a_memory_to_its_prior_version(db, settings):
    good = await write(db, "location: Bangalore")
    poison = await write(db, "location: Mars", memory_id=good.memory_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await run_rollback(db, poisoned_version_id=poison.version_id, triggered_by="test", settings=settings)
    await db.commit()

    assert [o.outcome for o in result.affected] == ["reverted"]
    assert await _current_text(db, good.memory_id) == "location: Bangalore"
    # Never mutates: the poisoned version is still in history.
    assert (await db.get(MemoryVersion, poison.version_id)).text == "location: Mars"
    assert not (await merkle.verify_integrity(db)).tampered


async def test_child_with_an_independent_parent_is_kept(db, settings):
    poison = await write(db, "preference: Python")
    independent = await write(db, "skill: Python")
    child = await write(db, "goal: learn Django")
    await graph.record_edge(db, parent_version_id=poison.version_id, child_version_id=child.version_id)
    await graph.record_edge(db, parent_version_id=independent.version_id, child_version_id=child.version_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await run_rollback(db, poisoned_version_id=poison.version_id, triggered_by="test", settings=settings)
    await db.commit()

    outcomes = {o.version_id: o.outcome for o in result.affected}
    assert outcomes == {poison.version_id: "removed", child.version_id: "kept"}
    assert (await db.get(Memory, child.memory_id)).status != "rolled_back"
    assert (await db.get(Memory, poison.memory_id)).status == "rolled_back"


async def test_rolling_back_a_superseded_version_keeps_newer_state_and_recovers_descendants(db, settings):
    # Regression (audit A6): rolling back a stale version used to revert its
    # memory to the stale version's predecessor, destroying the newer state.
    v1 = await write(db, "location: Delhi")
    poisoned = await write(db, "location: Kolkata", memory_id=v1.memory_id)
    child = await write(db, "goal: move to Kolkata")
    await graph.record_edge(db, parent_version_id=poisoned.version_id, child_version_id=child.version_id)
    # The update copies poisoned -> child onto the new version (carry-forward).
    await write(db, "location: Hyderabad", memory_id=v1.memory_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await run_rollback(db, poisoned_version_id=poisoned.version_id, triggered_by="test", settings=settings)
    await db.commit()

    outcomes = {o.version_id: o.outcome for o in result.affected}
    assert outcomes[poisoned.version_id] == "superseded"
    # The copied edge on the newer version must not count as independent support.
    assert outcomes[child.version_id] == "removed"
    assert await _current_text(db, v1.memory_id) == "location: Hyderabad"
    assert (await db.get(Memory, v1.memory_id)).status != "rolled_back"
    assert (await db.get(Memory, child.memory_id)).status == "rolled_back"
    assert not (await merkle.verify_integrity(db)).tampered


async def test_child_derived_before_the_poisoned_version_is_kept(db, settings):
    # The child came from legit v1; the poisoned v2 only carries a copy of that edge.
    original = await write(db, "preference: Python")
    child = await write(db, "goal: learn Django")
    await graph.record_edge(db, parent_version_id=original.version_id, child_version_id=child.version_id)
    poisoned = await write(db, "preference: not Python", memory_id=original.memory_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await run_rollback(db, poisoned_version_id=poisoned.version_id, triggered_by="test", settings=settings)
    await db.commit()

    outcomes = {o.version_id: o.outcome for o in result.affected}
    assert outcomes == {poisoned.version_id: "reverted", child.version_id: "kept"}
    assert await _current_text(db, original.memory_id) == "preference: Python"
    # The outcome names what was undone; the reason names what it went back to.
    reverted = next(o for o in result.affected if o.version_id == poisoned.version_id)
    assert reverted.text == "preference: not Python"
    assert '"preference: Python"' in reverted.reason
    assert (await db.get(Memory, child.memory_id)).status != "rolled_back"


async def test_descendant_is_not_reverted_to_an_older_poison_derived_version(db, settings):
    # The child memory was created from the poison, so its older version is
    # tainted too: "reverting" to it would restore poison-derived content.
    poisoned = await write(db, "preference: Python")
    child_v1 = await write(db, "goal: learn Django")
    await graph.record_edge(db, parent_version_id=poisoned.version_id, child_version_id=child_v1.version_id)
    child_v2 = await write(db, "goal: learn Django 5", memory_id=child_v1.memory_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await run_rollback(db, poisoned_version_id=poisoned.version_id, triggered_by="test", settings=settings)
    await db.commit()

    outcomes = {o.version_id: o.outcome for o in result.affected}
    assert outcomes[child_v1.version_id] == "superseded"
    assert outcomes[child_v2.version_id] == "removed"
    assert (await db.get(Memory, child_v1.memory_id)).status == "rolled_back"



async def test_concurrent_rollbacks_of_the_same_version_do_not_collide(db, session_factory, settings):
    # Regression: a double-clicked rollback ran twice on the same
    # pre-rollback state; the second tried to add a second active version
    # and failed with a 500 (unique index violation).
    seeded = await write(db, "preference: Python")
    await merkle.compute_and_store_root(db)
    await db.commit()
    version_id, memory_id = seeded.version_id, seeded.memory_id

    async def rollback_in_own_session():
        async with session_factory() as session:
            result = await run_rollback(session, poisoned_version_id=version_id, triggered_by="test", settings=settings)
            await session.commit()
            return [o.outcome for o in result.affected]

    outcomes = await asyncio.gather(rollback_in_own_session(), rollback_in_own_session())

    assert sorted(outcomes) == [["removed"], ["superseded"]]
    async with session_factory() as fresh:
        active = (
            await fresh.execute(
                sa.select(sa.func.count())
                .select_from(MemoryVersion)
                .where(MemoryVersion.memory_id == memory_id, MemoryVersion.is_active.is_(True))
            )
        ).scalar_one()
        assert active == 1
        assert not (await merkle.verify_integrity(fresh)).tampered


async def test_write_version_sees_a_concurrent_update_made_while_it_waited(db, session_factory):
    # write_version used to reuse the session's cached memory row after
    # acquiring FOR UPDATE, missing a version committed by another writer.
    first = await write(db, "location: Delhi")
    await db.commit()
    memory_id = first.memory_id
    # Hold the Memory object, as rollback's _process_node does: the session's
    # identity map is weak-referenced, so an unreferenced object would be
    # reloaded fresh anyway and hide the bug.
    cached = await db.get(Memory, memory_id)

    async with session_factory() as other:
        await write(other, "location: Mumbai", memory_id=memory_id)
        await other.commit()

    latest = await write(db, "location: Pune", memory_id=memory_id)
    await db.commit()

    assert latest.version_number == 3
    assert cached.current_version_id == latest.version_id
    assert await _current_text(db, memory_id) == "location: Pune"


async def test_write_version_refuses_when_the_expected_current_version_changed(db):
    from app.services.versioning import ConcurrentUpdateError, write_version

    v1 = await write(db, "location: Delhi")
    await db.commit()

    with pytest.raises(ConcurrentUpdateError):
        await write_version(
            db,
            memory_id=v1.memory_id,
            text="x",
            embedding=[0.0] * 384,
            trust_score=0.0,
            trust_breakdown={},
            decision="reject",
            provenance_fields={
                "conversation_id": v1.memory_id,
                "source_type": "admin_override",
                "model_version": None,
                "created_by": "test",
                "raw_input": None,
            },
            expected_current_version_id=uuid.uuid4(),
        )


async def test_repeating_a_rollback_writes_nothing_new(db, settings):
    await demo_seed.seed_demo(db, settings)
    await db.commit()
    root = (
        await db.execute(sa.select(MemoryVersion).where(MemoryVersion.text == "preference: Python"))
    ).scalar_one()
    root_id = root.version_id

    await run_rollback(db, poisoned_version_id=root_id, triggered_by="test", settings=settings)
    await db.commit()
    versions_after_first = (await db.execute(sa.select(sa.func.count()).select_from(MemoryVersion))).scalar_one()

    again = await run_rollback(db, poisoned_version_id=root_id, triggered_by="test", settings=settings)
    await db.commit()

    assert (await db.execute(sa.select(sa.func.count()).select_from(MemoryVersion))).scalar_one() == versions_after_first
    assert {o.outcome for o in again.affected} <= {"superseded", "removed"}
    assert not (await merkle.verify_integrity(db)).tampered
