from __future__ import annotations

import hashlib
import json


def compute_content_hash(text: str, embedding: list[float], provenance: dict) -> str:
    """sha256(text || embedding_bytes || provenance) -- DESIGN.md 6.8.

    Stored on memory_versions.content_hash at write time; reused unchanged
    by the Merkle tree service (Phase 5) as each leaf's hash.
    """
    embedding_bytes = "".join(f"{x:.8f}" for x in embedding).encode()
    provenance_bytes = json.dumps(provenance, sort_keys=True, default=str).encode()
    payload = text.encode() + embedding_bytes + provenance_bytes
    return hashlib.sha256(payload).hexdigest()
