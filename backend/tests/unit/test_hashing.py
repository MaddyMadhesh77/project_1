from app.services.hashing import compute_content_hash

_PROVENANCE = {
    "conversation_id": "c1",
    "source_type": "user",
    "model_version": None,
    "created_by": "user",
    "raw_input": "hi",
}


def test_hash_is_deterministic_for_identical_inputs():
    embedding = [0.1, 0.2, 0.3]
    assert compute_content_hash("preference: Python", embedding, _PROVENANCE) == compute_content_hash(
        "preference: Python", list(embedding), _PROVENANCE
    )


def test_hash_changes_for_a_text_edit():
    embedding = [0.1, 0.2, 0.3]
    original = compute_content_hash("preference: Python", embedding, _PROVENANCE)
    tampered = compute_content_hash("preference: Python [TAMPERED]", embedding, _PROVENANCE)
    assert original != tampered


def test_hash_changes_for_an_embedding_difference():
    a = compute_content_hash("preference: Python", [0.1, 0.2, 0.3], _PROVENANCE)
    b = compute_content_hash("preference: Python", [0.1, 0.2, 0.4], _PROVENANCE)
    assert a != b


def test_hash_is_sensitive_to_tiny_embedding_differences():
    # By design (DESIGN.md 6.8): this function hashes whatever `embedding`
    # it's given at full precision, with no tolerance built in. That means
    # callers MUST pass the same representation at write time and at verify
    # time -- see services/versioning.py, which refreshes the embedding from
    # the DB before hashing specifically so both sides observe the exact
    # same as-stored bits (pgvector's vector column doesn't round-trip
    # floats bit-exactly, so hashing a pre-write in-memory value here would
    # silently disagree with a post-write DB-read value later).
    a = compute_content_hash("preference: Python", [-0.022904934361577034], _PROVENANCE)
    b = compute_content_hash("preference: Python", [-0.022904934], _PROVENANCE)
    assert a != b


def test_hash_changes_for_a_provenance_difference():
    embedding = [0.1, 0.2, 0.3]
    a = compute_content_hash("preference: Python", embedding, _PROVENANCE)
    b = compute_content_hash("preference: Python", embedding, {**_PROVENANCE, "raw_input": "different"})
    assert a != b
