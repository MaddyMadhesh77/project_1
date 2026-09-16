import uuid

from app.api.routes.chat import same_memory_match
from app.services.retrieval import RetrievalHit


def _hit(similarity: float, rrf: float) -> RetrievalHit:
    return RetrievalHit(
        memory_id=uuid.uuid4(), version_id=uuid.uuid4(), text="x", trust_score=80.0, similarity=similarity, rrf_score=rrf
    )


def test_picks_most_similar_hit_even_when_a_keyword_only_hit_ranks_first():
    # Regression (audit B12): hits[0] was a keyword-only hit (similarity 0.0),
    # so the real update target below was ignored and a duplicate was created.
    keyword_only = _hit(similarity=0.0, rrf=0.033)
    real_match = _hit(similarity=0.82, rrf=0.032)

    assert same_memory_match([keyword_only, real_match], threshold=0.5) is real_match


def test_no_match_below_threshold():
    assert same_memory_match([_hit(similarity=0.49, rrf=0.03)], threshold=0.5) is None


def test_no_hits():
    assert same_memory_match([], threshold=0.5) is None
