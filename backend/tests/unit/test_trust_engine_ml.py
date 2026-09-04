import pickle

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app.core.config import Settings
from app.services import model_integrity, trust_engine
from app.services.features import FEATURE_NAMES, FeatureVector
from app.services.trust_engine import ModelBundle


def _settings(**overrides):
    return Settings(**overrides)


def _contradiction_features() -> FeatureVector:
    return FeatureVector(
        similarity=0.8,
        contradiction=1.0,
        source_reliability=1.0,
        memory_age_days=1.0,
        prior_trust_score=70.0,
        corroboration_count=0,
        conversation_recency=1.0,
        has_match=True,
    )


def _trained_bundle(n_samples: int, n_real_samples: int | None = None) -> ModelBundle:
    # A real (tiny) RandomForestClassifier, not a mock -- exercises the actual
    # shap.TreeExplainer code path rather than a stubbed prediction. Trained
    # on a trivial rule (contradiction column low => safe) so predict_proba
    # is non-degenerate for the features used below.
    rng = np.random.default_rng(0)
    X = rng.random((40, len(FEATURE_NAMES)))
    contradiction_col = FEATURE_NAMES.index("contradiction")
    y = (X[:, contradiction_col] < 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
    # Defaults n_real_samples to n_samples so callers that don't care about
    # the synthetic/real distinction (most of these tests) get the old
    # "gate on total" behavior for free.
    return ModelBundle(
        model=model,
        n_samples=n_samples,
        n_real_samples=n_samples if n_real_samples is None else n_real_samples,
        trained_at="test",
    )


def test_below_min_training_samples_falls_back_to_rule_score(monkeypatch):
    bundle = _trained_bundle(n_samples=10)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50)
    features = _contradiction_features()

    rule_only = trust_engine._score_rule(features, settings)
    blended = trust_engine.score_candidate(features, settings)

    assert blended == rule_only


def test_missing_model_file_falls_back_to_rule_score(monkeypatch):
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: None)

    settings = _settings(min_training_samples=50)
    features = _contradiction_features()

    rule_only = trust_engine._score_rule(features, settings)
    blended = trust_engine.score_candidate(features, settings)

    assert blended == rule_only


def test_above_min_training_samples_blends_and_returns_shap_breakdown(monkeypatch):
    bundle = _trained_bundle(n_samples=100)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50, rf_blend_weight=0.5)
    features = _contradiction_features()

    result = trust_engine.score_candidate(features, settings)

    assert set(result.breakdown) == set(FEATURE_NAMES) | {"baseline"}
    assert result.decision in {"store", "review", "reject"}
    assert 0.0 <= result.score <= 100.0


def test_blend_weight_one_reduces_to_pure_rule_score(monkeypatch):
    bundle = _trained_bundle(n_samples=100)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50, rf_blend_weight=1.0)
    features = _contradiction_features()

    rule_only = trust_engine._score_rule(features, settings)
    blended = trust_engine.score_candidate(features, settings)

    assert blended.score == rule_only.score


def test_blend_weight_zero_reduces_to_pure_rf_score(monkeypatch):
    bundle = _trained_bundle(n_samples=100)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50, rf_blend_weight=0.0)
    features = _contradiction_features()

    proba_safe, _ = trust_engine._shap_breakdown(features, bundle)
    blended = trust_engine.score_candidate(features, settings)

    assert blended.score == round(100 * proba_safe, 2)


def test_synthetic_only_training_does_not_activate_the_rf_even_with_high_total(monkeypatch):
    # Regression guard: app/ml/data/synthetic_examples.json alone has enough
    # rows to clear a default min_training_samples=50 total, so a single
    # `python -m app.ml.train` run with zero real logged outcomes must NOT
    # activate RF blending -- only real signal should count toward the gate.
    bundle = _trained_bundle(n_samples=60, n_real_samples=0)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50)
    features = _contradiction_features()

    rule_only = trust_engine._score_rule(features, settings)
    blended = trust_engine.score_candidate(features, settings)

    assert blended == rule_only


def test_real_samples_below_gate_falls_back_even_with_high_total(monkeypatch):
    bundle = _trained_bundle(n_samples=200, n_real_samples=10)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50)
    features = _contradiction_features()

    rule_only = trust_engine._score_rule(features, settings)
    blended = trust_engine.score_candidate(features, settings)

    assert blended == rule_only


def test_real_samples_clearing_the_gate_activates_blending(monkeypatch):
    bundle = _trained_bundle(n_samples=200, n_real_samples=50)
    monkeypatch.setattr(trust_engine, "_load_bundle", lambda: bundle)

    settings = _settings(min_training_samples=50, rf_blend_weight=0.5)
    features = _contradiction_features()

    blended = trust_engine.score_candidate(features, settings)

    # SHAP breakdown keys (feature names + baseline) only appear via the RF
    # path -- the rule scorer's breakdown uses entirely different keys
    # (source/semantic_similarity/novelty/context/contradiction/corroboration)
    # -- so this confirms blending actually activated, not just that scoring
    # didn't crash.
    assert set(blended.breakdown) == set(FEATURE_NAMES) | {"baseline"}


def test_load_bundle_returns_none_when_model_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(trust_engine, "_MODEL_PATH", tmp_path / "does_not_exist.pkl")
    trust_engine.clear_model_cache()
    try:
        assert trust_engine._load_bundle() is None
    finally:
        trust_engine.clear_model_cache()


def test_load_bundle_reads_a_real_pickled_bundle(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    rf = RandomForestClassifier(n_estimators=5, random_state=0).fit([[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], [0, 1])
    with open(model_path, "wb") as f:
        pickle.dump(
            {"model": rf, "feature_names": FEATURE_NAMES, "n_samples": 42, "n_real_samples": 7, "trained_at": "t"}, f
        )

    monkeypatch.setattr(trust_engine, "_MODEL_PATH", model_path)
    trust_engine.clear_model_cache()
    try:
        bundle = trust_engine._load_bundle()
        assert bundle is not None
        assert bundle.n_samples == 42
        assert bundle.n_real_samples == 7
    finally:
        trust_engine.clear_model_cache()


def test_load_bundle_treats_missing_n_real_samples_as_zero(tmp_path, monkeypatch):
    # A model.pkl trained before n_real_samples existed (old train.py) has no
    # way to say how much of its data was real -- must fail closed (gate
    # stays shut) rather than guessing it was all real.
    model_path = tmp_path / "model.pkl"
    rf = RandomForestClassifier(n_estimators=5, random_state=0).fit([[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], [0, 1])
    with open(model_path, "wb") as f:
        pickle.dump({"model": rf, "feature_names": FEATURE_NAMES, "n_samples": 100, "trained_at": "t"}, f)

    monkeypatch.setattr(trust_engine, "_MODEL_PATH", model_path)
    trust_engine.clear_model_cache()
    try:
        bundle = trust_engine._load_bundle()
        assert bundle is not None
        assert bundle.n_real_samples == 0
    finally:
        trust_engine.clear_model_cache()


def _write_bundle(model_path, n_samples: int = 1) -> None:
    rf = RandomForestClassifier(n_estimators=5, random_state=0).fit(
        [[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], [0, 1]
    )
    with open(model_path, "wb") as f:
        pickle.dump(
            {
                "model": rf,
                "feature_names": FEATURE_NAMES,
                "n_samples": n_samples,
                "n_real_samples": n_samples,
                "trained_at": "t",
            },
            f,
        )


def test_load_bundle_with_signing_key_accepts_a_correctly_signed_model(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    _write_bundle(model_path)
    model_integrity.write_signature(model_path, "s3cr3t")

    monkeypatch.setattr(trust_engine, "_MODEL_PATH", model_path)
    monkeypatch.setattr(trust_engine, "get_settings", lambda: _settings(model_signing_key="s3cr3t"))
    trust_engine.clear_model_cache()
    try:
        assert trust_engine._load_bundle() is not None
    finally:
        trust_engine.clear_model_cache()


def test_load_bundle_with_signing_key_rejects_a_tampered_model(tmp_path, monkeypatch):
    # Simulates an attacker replacing model.pkl after it was signed: the
    # pickle.load arbitrary-code-execution path must never be reached for a
    # file that doesn't match its signature.
    model_path = tmp_path / "model.pkl"
    _write_bundle(model_path)
    model_integrity.write_signature(model_path, "s3cr3t")
    _write_bundle(model_path, n_samples=999)  # overwritten after signing, .sig now stale

    monkeypatch.setattr(trust_engine, "_MODEL_PATH", model_path)
    monkeypatch.setattr(trust_engine, "get_settings", lambda: _settings(model_signing_key="s3cr3t"))
    trust_engine.clear_model_cache()
    try:
        assert trust_engine._load_bundle() is None
    finally:
        trust_engine.clear_model_cache()


def test_load_bundle_with_signing_key_rejects_a_missing_signature(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    _write_bundle(model_path)  # no .sig written at all

    monkeypatch.setattr(trust_engine, "_MODEL_PATH", model_path)
    monkeypatch.setattr(trust_engine, "get_settings", lambda: _settings(model_signing_key="s3cr3t"))
    trust_engine.clear_model_cache()
    try:
        assert trust_engine._load_bundle() is None
    finally:
        trust_engine.clear_model_cache()
