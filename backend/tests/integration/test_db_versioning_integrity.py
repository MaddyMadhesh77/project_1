"""write_version -> Merkle root -> verify_integrity against a real database."""
from __future__ import annotations

import sqlalchemy as sa
from factories import write

from app.models import Memory, MemoryVersion, Provenance
from app.services import merkle
from app.services.hashing import compute_content_hash


async def test_update_versions_instead_of_overwriting(db):
    v1 = await write(db, "location: Bangalore")
    v2 = await write(db, "location: Mumbai", memory_id=v1.memory_id, decision="reject", trust_score=20.0)
    await db.commit()

    versions = (
        await db.execute(sa.select(MemoryVersion).where(MemoryVersion.memory_id == v1.memory_id))
    ).scalars().all()
    memory = await db.get(Memory, v1.memory_id)

    assert sorted((v.version_number, v.is_active) for v in versions) == [(1, False), (2, True)]
    # Even a rejected update becomes current -- flagged via status, prior version intact.
    assert memory.current_version_id == v2.version_id
    assert memory.status == "quarantined"
    assert (await db.get(MemoryVersion, v1.version_id)).text == "location: Bangalore"


async def test_content_hash_survives_a_db_round_trip(db, session_factory):
    # Regression (Phase 5): pgvector doesn't round-trip floats bit-exactly, so
    # the hash must be computed from the as-stored embedding.
    versions = [await write(db, f"skill: language {i}") for i in range(20)]
    await db.commit()

    async with session_factory() as fresh:
        for v in versions:
            stored = await fresh.get(MemoryVersion, v.version_id)
            prov = (
                await fresh.execute(sa.select(Provenance).where(Provenance.version_id == v.version_id))
            ).scalar_one()
            fields = {
                "conversation_id": prov.conversation_id,
                "source_type": prov.source_type,
                "model_version": prov.model_version,
                "created_by": prov.created_by,
                "raw_input": prov.raw_input,
            }
            assert compute_content_hash(stored.text, list(stored.embedding), fields) == stored.content_hash


async def test_verify_is_clean_after_normal_writes(db):
    v1 = await write(db, "preference: Python")
    await write(db, "preference: Rust", memory_id=v1.memory_id)
    await write(db, "location: Chennai")
    await merkle.compute_and_store_root(db)
    await db.commit()

    result = await merkle.verify_integrity(db)

    assert not result.tampered
    assert result.leaf_count == 2  # active versions only


async def test_verify_detects_in_place_edit_of_current_version(db):
    v = await write(db, "location: Pune")
    await merkle.compute_and_store_root(db)
    await db.commit()

    await db.execute(sa.text("UPDATE memory_versions SET text = 'location: Mars' WHERE version_id = :id"), {"id": v.version_id})
    await db.commit()
    result = await merkle.verify_integrity(db)

    assert result.tampered
    assert [m.version_id for m in result.row_mismatches] == [v.version_id]
    assert result.root_mismatch


async def test_verify_detects_in_place_edit_of_superseded_version(db):
    # Regression (audit A5): only active versions used to be scanned.
    v1 = await write(db, "preference: Go")
    await write(db, "preference: Zig", memory_id=v1.memory_id)
    await merkle.compute_and_store_root(db)
    await db.commit()

    await db.execute(sa.text("UPDATE memory_versions SET text = 'preference: COBOL' WHERE version_id = :id"), {"id": v1.version_id})
    await db.commit()
    result = await merkle.verify_integrity(db)

    assert result.tampered
    assert [m.version_id for m in result.row_mismatches] == [v1.version_id]
    assert not result.root_mismatch  # superseded versions aren't Merkle leaves


async def test_verify_reports_version_with_deleted_provenance(db):
    v = await write(db, "goal: learn Haskell")
    await merkle.compute_and_store_root(db)
    await db.commit()

    await db.execute(sa.delete(Provenance).where(Provenance.version_id == v.version_id))
    await db.commit()
    result = await merkle.verify_integrity(db)

    assert result.tampered
    assert result.orphaned_version_ids == [v.version_id]
    assert result.row_mismatches == []


async def test_several_roots_in_one_transaction_leave_verify_clean(db):
    # Regression (Phase 8): roots written in one transaction shared a
    # timestamp, and latest_root() could pick a stale mid-transaction one.
    for i in range(3):
        await write(db, f"skill: tool {i}")
        await merkle.compute_and_store_root(db)
    await db.commit()

    assert not (await merkle.verify_integrity(db)).tampered
