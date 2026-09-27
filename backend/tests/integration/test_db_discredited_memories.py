"""Memories the trust gate rejected (quarantined) or a rollback purged
(rolled_back) must not keep influencing new memories."""
from __future__ import annotations

import uuid

from factories import fake_embedding, write

from app.models import Memory
from app.services import retrieval
from app.services.features import _count_corroborating
from app.services.rollback import run_rollback


async def _corroboration(db, exclude_memory_id=None) -> int:
    return await _count_corroborating(
        db, predicate="preference", value="Java", polarity=1, exclude_memory_id=exclude_memory_id or uuid.uuid4()
    )


async def test_trusted_memories_corroborate(db):
    await write(db, "preference: Java")
    await db.commit()
    assert await _corroboration(db) == 1


async def test_quarantined_memory_does_not_corroborate(db):
    # The trust gate rejected it; repeating a rejected claim must not raise
    # the trust of the next copy (corroboration laundering).
    await write(db, "preference: Java", decision="reject", trust_score=20.0)
    await db.commit()
    assert await _corroboration(db) == 0


async def test_rolled_back_memory_does_not_corroborate_or_get_retrieved(db, settings):
    poison = await write(db, "preference: Java")
    await db.commit()
    await run_rollback(db, poisoned_version_id=poison.version_id, triggered_by="test", settings=settings)
    await db.commit()
    assert (await db.get(Memory, poison.memory_id)).status == "rolled_back"

    assert await _corroboration(db) == 0
    hits = await retrieval.hybrid_search(
        db, embedding=fake_embedding("preference: Java"), text="preference: Java", top_k=5
    )
    assert [h.memory_id for h in hits if h.memory_id == poison.memory_id] == []


async def test_quarantined_memory_is_still_retrieved(db):
    # A rejected update is still the memory's current (flagged) state: a later
    # statement on the same topic must find it so it versions that memory and
    # contradiction detection sees it.
    quarantined = await write(db, "location: Mars", decision="reject", trust_score=20.0)
    await db.commit()
    hits = await retrieval.hybrid_search(db, embedding=fake_embedding("location: Mars"), text="location: Mars", top_k=5)
    assert [h.memory_id for h in hits] == [quarantined.memory_id]
