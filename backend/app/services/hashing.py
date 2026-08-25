from __future__ import annotations

import hashlib
import json


def compute_content_hash(text: str, embedding: list[float], provenance: dict) -> str:
    """sha256(text || embedding_bytes || provenance) -- DESIGN.md 6.8.

    Stored on memory_versions.content_hash at write time; reused unchanged
    by the Merkle tree service (Phase 5) as each leaf's hash, and recomputed
    from current row content by Phase 5's verify_integrity for tamper
    detection. `embedding` must be the value as Postgres's `vector` column
    actually stores/returns it, not a freshly-computed one -- pgvector's
    text round-trip is not bit-exact (empirically ~1e-9 absolute noise per
    component, well inside float32 precision but enough to occasionally flip
    a formatted digit across 384 components). services/versioning.py handles
    this by refreshing the version's `embedding` attribute from the DB
    before computing the hash, so write-time and verify-time always hash
    identical bits by construction -- fixed-precision formatting here was
    tried first and wasn't a reliable enough fix on its own (see git history
    on this function / PLAN.md's Phase 5 notes).
    """
    embedding_bytes = "".join(repr(x) for x in embedding).encode()
    provenance_bytes = json.dumps(provenance, sort_keys=True, default=str).encode()
    payload = text.encode() + embedding_bytes + provenance_bytes
    return hashlib.sha256(payload).hexdigest()
