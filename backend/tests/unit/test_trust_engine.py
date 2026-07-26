from app.core.config import Settings
from app.services.features import FeatureVector
from app.services.trust_engine import score_candidate


def _settings(**overrides):
    return Settings(**overrides)


def test_novel_uncontested_fact_is_stored():
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
    result = score_candidate(features, _settings())
    assert result.decision == "store"
    assert result.breakdown["novelty"] == 24.0
    assert result.breakdown["semantic_similarity"] == 0.0


def test_hard_contradiction_against_trusted_memory_is_downgraded():
    features = FeatureVector(
        similarity=0.85,
        contradiction=1.0,
        source_reliability=1.0,
        memory_age_days=1.0,
        prior_trust_score=72.0,
        corroboration_count=0,
        conversation_recency=1.0,
        has_match=True,
    )
    result = score_candidate(features, _settings())
    assert result.decision in {"review", "reject"}
    assert result.breakdown["contradiction"] < 0
    assert result.score < 70


def test_corroborating_update_scores_higher_than_contradicting_one():
    base = dict(
        similarity=0.85,
        source_reliability=1.0,
        memory_age_days=1.0,
        prior_trust_score=72.0,
        corroboration_count=0,
        conversation_recency=1.0,
        has_match=True,
    )
    corroborating = score_candidate(FeatureVector(contradiction=0.0, **base), _settings())
    contradicting = score_candidate(FeatureVector(contradiction=1.0, **base), _settings())
    assert corroborating.score > contradicting.score
    assert corroborating.decision == "store"


def test_score_is_clamped_to_0_100():
    features = FeatureVector(
        similarity=1.0,
        contradiction=0.0,
        source_reliability=1.0,
        memory_age_days=0.0,
        prior_trust_score=100.0,
        corroboration_count=5,
        conversation_recency=1.0,
        has_match=True,
    )
    result = score_candidate(features, _settings())
    assert 0.0 <= result.score <= 100.0


def test_decision_thresholds_are_configurable():
    features = FeatureVector(
        similarity=0.0,
        contradiction=0.0,
        source_reliability=0.4,
        memory_age_days=0.0,
        prior_trust_score=0.0,
        corroboration_count=0,
        conversation_recency=1.0,
        has_match=False,
    )
    lenient = score_candidate(features, _settings(trust_threshold_store=10.0))
    strict = score_candidate(features, _settings(trust_threshold_store=99.0))
    assert lenient.decision == "store"
    assert strict.decision != "store"


def test_corroboration_capped_at_two_matches():
    base = dict(
        similarity=0.0,
        contradiction=0.0,
        source_reliability=1.0,
        memory_age_days=0.0,
        prior_trust_score=0.0,
        conversation_recency=1.0,
        has_match=False,
    )
    two_matches = score_candidate(FeatureVector(corroboration_count=2, **base), _settings())
    five_matches = score_candidate(FeatureVector(corroboration_count=5, **base), _settings())
    assert two_matches.breakdown["corroboration"] == 20.0
    assert five_matches.breakdown["corroboration"] == 20.0
