from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemoryVersion, MerkleRoot, Provenance
from app.services.hashing import compute_content_hash


def build_root(leaf_hashes: list[str]) -> str:
    """Bottom-up Merkle root over leaf hashes, in the given order (DESIGN.md
    6.8). An odd node at any level is paired with itself (standard Merkle
    padding) so the tree always resolves to a single root regardless of leaf
    count. Empty input hashes to sha256("") so an empty store still has a
    well-defined root to compare against.
    """
    if not leaf_hashes:
        return hashlib.sha256(b"").hexdigest()

    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256((level[i] + level[i + 1]).encode()).hexdigest() for i in range(0, len(level), 2)]
    return level[0]


async def _active_leaf_hashes(db: AsyncSession) -> list[str]:
    """Leaf hash per active version = the stored `content_hash` column,
    ordered by version_id (DESIGN.md 5, 6.8)."""
    rows = (
        await db.execute(
            sa.select(MemoryVersion.content_hash)
            .where(MemoryVersion.is_active.is_(True))
            .order_by(MemoryVersion.version_id)
        )
    ).scalars().all()
    return list(rows)


async def compute_and_store_root(db: AsyncSession) -> MerkleRoot:
    """Recompute the root over all currently-active leaves and append a new
    merkle_roots row. Called from services/versioning.py on every write so
    the root history stays exactly in sync with the store (DESIGN.md 6.8:
    "root stored in merkle_roots on every batch of writes")."""
    leaves = await _active_leaf_hashes(db)
    root = MerkleRoot(root_hash=build_root(leaves), leaf_count=len(leaves))
    db.add(root)
    await db.flush()
    return root


async def latest_root(db: AsyncSession) -> MerkleRoot | None:
    # sequence_number, not computed_at -- see migration 8b2e5f6a1c9d.
    return (
        await db.execute(sa.select(MerkleRoot).order_by(MerkleRoot.sequence_number.desc()).limit(1))
    ).scalars().first()


@dataclass
class TamperedVersion:
    version_id: uuid.UUID
    memory_id: uuid.UUID
    stored_hash: str
    recomputed_hash: str


@dataclass
class VerifyResult:
    tampered: bool
    row_mismatches: list[TamperedVersion] = field(default_factory=list)
    orphaned_version_ids: list[uuid.UUID] = field(default_factory=list)
    root_mismatch: bool = False
    expected_root: str | None = None
    actual_root: str = ""
    leaf_count: int = 0


async def verify_integrity(db: AsyncSession) -> VerifyResult:
    """DESIGN.md 6.8 "Verify Integrity": for every active version, recompute
    `sha256(text || embedding_bytes || provenance)` from the row's CURRENT
    content and compare to the stored `content_hash` column (row-level
    tamper -- e.g. a DBA hand-editing `text` in place, which is exactly what
    POST /attack/tamper-db simulates and does NOT update content_hash). Then
    rebuild the tree from those recomputed hashes -- not the stored
    content_hash values, which a row-level tamper leaves untouched -- and
    compare the root to the latest merkle_roots row (structural tamper:
    added/removed/reordered rows, or exactly the root-level symptom of a
    row-level tamper). Read-only: a mismatch is reported, never silently
    "healed" by writing a new root over the evidence.

    Deliberately a full O(N) scan + recompute over every active version, not
    an incrementally-cached check: fine at demo scale, but it's the one place
    in this codebase where "only re-verify what changed since last time"
    isn't a safe shortcut to take without other infrastructure -- there's no
    reliable, tamper-proof "this row changed" signal to key off (an
    out-of-band UPDATE like POST /attack/tamper-db doesn't bump any
    updated_at/version marker, which is exactly the kind of tamper this
    exists to catch). Skipping unchanged-looking rows would mean trusting the
    same channel an attacker who can write directly to the table already
    controls. A real fix would need something like DB-level change-tracking
    (triggers, WAL/CDC) feeding an already-verified-as-of-root cache -- out of
    scope here since it changes the trust model, not just the algorithm.

    Uses a LEFT JOIN on Provenance rather than an INNER JOIN: an active
    version with no provenance row (e.g. a direct DB insert, or a future code
    path that forgets to write one) must still show up here and count toward
    leaf_count -- an INNER JOIN makes such a row invisible to integrity
    checking entirely, which is itself a silent-corruption path. Since there's
    no provenance to recompute sha256(text || embedding || provenance) from,
    an orphan can't be hash-verified; it's reported separately and always
    counts as tampered.
    """
    rows = (
        await db.execute(
            sa.select(MemoryVersion, Provenance)
            .outerjoin(Provenance, Provenance.version_id == MemoryVersion.version_id)
            .where(MemoryVersion.is_active.is_(True))
            .order_by(MemoryVersion.version_id)
        )
    ).all()

    row_mismatches: list[TamperedVersion] = []
    orphaned_version_ids: list[uuid.UUID] = []
    recomputed_hashes: list[str] = []
    for version, provenance in rows:
        if provenance is None:
            orphaned_version_ids.append(version.version_id)
            # Can't recompute without provenance -- fall back to the stored
            # hash so the leaf still participates in the root, rather than
            # vanishing from the tree the way the INNER JOIN made it vanish
            # from this whole query.
            recomputed_hashes.append(version.content_hash)
            continue

        provenance_fields = {
            "conversation_id": provenance.conversation_id,
            "source_type": provenance.source_type,
            "model_version": provenance.model_version,
            "created_by": provenance.created_by,
            "raw_input": provenance.raw_input,
        }
        recomputed = compute_content_hash(version.text, list(version.embedding), provenance_fields)
        recomputed_hashes.append(recomputed)
        if recomputed != version.content_hash:
            row_mismatches.append(
                TamperedVersion(
                    version_id=version.version_id,
                    memory_id=version.memory_id,
                    stored_hash=version.content_hash,
                    recomputed_hash=recomputed,
                )
            )

    actual_root = build_root(recomputed_hashes)
    latest = await latest_root(db)
    expected_root = latest.root_hash if latest else None
    root_mismatch = expected_root is not None and actual_root != expected_root

    return VerifyResult(
        tampered=bool(row_mismatches) or bool(orphaned_version_ids) or root_mismatch,
        row_mismatches=row_mismatches,
        orphaned_version_ids=orphaned_version_ids,
        root_mismatch=root_mismatch,
        expected_root=expected_root,
        actual_root=actual_root,
        leaf_count=len(recomputed_hashes),
    )
