import hashlib

from app.services.hashing import compute_content_hash
from app.services.merkle import build_root


def test_empty_store_has_well_defined_root():
    assert build_root([]) == hashlib.sha256(b"").hexdigest()


def test_root_is_deterministic_for_same_leaves():
    leaves = ["a" * 64, "b" * 64, "c" * 64]
    assert build_root(leaves) == build_root(list(leaves))


def test_root_changes_if_any_leaf_changes():
    leaves = ["a" * 64, "b" * 64, "c" * 64]
    tampered = ["a" * 64, "b" * 64, "d" * 64]
    assert build_root(leaves) != build_root(tampered)


def test_root_changes_if_leaf_order_changes():
    leaves = ["a" * 64, "b" * 64, "c" * 64]
    reordered = ["c" * 64, "a" * 64, "b" * 64]
    assert build_root(leaves) != build_root(reordered)


def test_odd_leaf_count_still_resolves_to_single_root():
    # Regression guard: an unpadded pairwise reduction over an odd-length
    # level would silently drop the last leaf instead of raising or padding.
    single = build_root(["a" * 64])
    three = build_root(["a" * 64, "b" * 64, "c" * 64])
    five = build_root(["a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64])
    assert single and three and five
    assert len({single, three, five}) == 3


def test_row_level_tamper_changes_recomputed_hash():
    # Simulates POST /attack/tamper-db: text mutated in place, content_hash
    # column left untouched -- verify_integrity's recompute-and-compare is
    # exactly what should catch this (DESIGN.md 6.8).
    embedding = [0.1, 0.2, 0.3]
    provenance = {"conversation_id": "c1", "source_type": "user", "model_version": None, "created_by": "user", "raw_input": "hi"}

    stored_hash = compute_content_hash("preference: Python", embedding, provenance)
    tampered_hash = compute_content_hash("preference: Python [TAMPERED]", embedding, provenance)

    assert stored_hash != tampered_hash
    # And the store-wide root reacts too, not just the single leaf.
    assert build_root([stored_hash]) != build_root([tampered_hash])
