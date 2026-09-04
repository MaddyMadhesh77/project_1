from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.services import model_integrity
from app.services.features import FEATURE_NAMES, FeatureVector, to_vector

logger = logging.getLogger(__name__)

# Additive rule-scorer weights: Settings.trust_weight_* (see config.py for
# the relative-magnitude rationale). This is the "always available, no
# training data needed" layer -- Phase 7 blends a RandomForest+SHAP layer on
# top of _score_rule's output, gated by min_training_samples so an
# undertrained model can't dominate a demo.

_MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "model.pkl"


@dataclass
class TrustResult:
    score: float
    breakdown: dict[str, float]
    decision: str  # store | review | reject


def _decide(total: float, settings: Settings) -> str:
    if total >= settings.trust_threshold_store:
        return "store"
    if total >= settings.trust_threshold_review:
        return "review"
    return "reject"


def _score_rule(features: FeatureVector, settings: Settings) -> TrustResult:
    """Deterministic additive rule scorer producing the trust_breakdown JSON
    shown in the dashboard (DESIGN.md 6.5's `source +30 / semantic_similarity
    +24 / ...` example). Pure function of the feature vector + configured
    thresholds -- no DB/model access, so this is the easiest place to unit
    test the scoring math and threshold branching in isolation, and it's
    always available even before Phase 7's model is ever trained.
    """
    source = round(settings.trust_weight_source * features.source_reliability, 1)
    semantic_similarity = round(settings.trust_weight_similarity * features.similarity, 1) if features.has_match else 0.0
    novelty = 0.0 if features.has_match else settings.trust_weight_novelty_bonus
    context = round(settings.trust_weight_context * features.conversation_recency, 1)

    if features.has_match and features.contradiction > 0:
        # Older/more-trusted memories require stronger evidence to overturn
        # (DESIGN.md 6.4) -- scale the penalty by how trusted the thing being
        # contradicted currently is.
        trust_weight = 0.5 + 0.5 * (features.prior_trust_score / 100)
        contradiction = round(-settings.trust_weight_contradiction * features.contradiction * trust_weight, 1)
    else:
        contradiction = 0.0

    # A consistent restatement of the matched memory (no contradiction) is
    # itself a corroborating signal, on top of any other independent memories
    # already counted in corroboration_count -- otherwise a plain, uncontested
    # reaffirmation of an existing fact would score *below* a brand-new one
    # (which gets the novelty bonus instead), which has it backwards.
    self_corroboration = 1 if features.has_match and features.contradiction == 0 else 0
    corroboration = round(
        min(
            settings.trust_weight_corroboration_cap,
            (features.corroboration_count + self_corroboration) * settings.trust_weight_corroboration_per_match,
        ),
        1,
    )

    breakdown = {
        "source": source,
        "semantic_similarity": semantic_similarity,
        "novelty": novelty,
        "context": context,
        "contradiction": contradiction,
        "corroboration": corroboration,
    }
    total = max(0.0, min(100.0, sum(breakdown.values())))

    return TrustResult(score=round(total, 2), breakdown=breakdown, decision=_decide(total, settings))


@dataclass
class ModelBundle:
    model: Any  # sklearn.ensemble.RandomForestClassifier
    n_samples: int  # synthetic + real logged, i.e. what the model was actually fit on
    n_real_samples: int  # real logged only -- what min_training_samples gates on
    trained_at: str


@lru_cache
def _load_bundle() -> ModelBundle | None:
    """Loads app/ml/model.pkl if app/ml/train.py has ever been run. Returns
    None (cold start) otherwise, so scoring degrades gracefully to the rule
    engine alone -- training is a manual step (PLAN.md Phase 7), never a
    precondition for the demo to run at all. Cached per-process: call
    trust_engine.clear_model_cache() after retraining to pick up a new
    model.pkl without restarting the server.
    """
    if not _MODEL_PATH.exists():
        return None

    signing_key = get_settings().model_signing_key
    if signing_key:
        if not model_integrity.verify(_MODEL_PATH, signing_key):
            # Refuse to unpickle an unsigned/mismatched file rather than risk
            # arbitrary code execution from a replaced model.pkl -- degrade to
            # the always-available rule scorer instead of crashing the caller.
            logger.error(
                "app/ml/model.pkl failed signature verification -- refusing to load it. "
                "Retrain with `python -m app.ml.train` (MODEL_SIGNING_KEY set) to regenerate "
                "a matching model.pkl.sig. Falling back to the rule-only trust scorer."
            )
            return None
    else:
        logger.warning(
            "MODEL_SIGNING_KEY is not set -- app/ml/model.pkl is being loaded without integrity "
            "verification. Set MODEL_SIGNING_KEY to detect a tampered or maliciously replaced model file "
            "before it's unpickled."
        )

    with open(_MODEL_PATH, "rb") as f:
        raw = pickle.load(f)
    return ModelBundle(
        model=raw["model"],
        n_samples=raw["n_samples"],
        # .get(..., 0): a model.pkl trained before this field existed has no
        # way to know how much of its training data was real vs. the fixed
        # synthetic bootstrap set -- treat it as 0 real samples (gate stays
        # closed) rather than guessing, until it's retrained.
        n_real_samples=raw.get("n_real_samples", 0),
        trained_at=raw["trained_at"],
    )


def clear_model_cache() -> None:
    _load_bundle.cache_clear()


def _shap_breakdown(features: FeatureVector, bundle: ModelBundle) -> tuple[float, dict[str, float]]:
    """Real per-feature SHAP contributions toward P(safe) from the trained
    RF (DESIGN.md 6.5 part 2), scaled to the same 0-100 "points" register the
    rule scorer's breakdown uses. shap.TreeExplainer guarantees
    sum(shap_values) + expected_value == predict_proba (verified against
    shap 0.52's shap_values(x) shape for a binary RandomForestClassifier:
    (n_samples, n_features, n_classes)), so these contributions plus
    "baseline" are an exact, not approximate, decomposition of the model's
    own P(safe) -- this is what makes the breakdown genuinely explainable AI
    rather than a canned bar chart once the RF is live.
    """
    import numpy as np
    import shap

    x = np.array([to_vector(features)])
    model = bundle.model
    class1_idx = list(model.classes_).index(1)
    proba_safe = float(model.predict_proba(x)[0][class1_idx])

    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(x)  # shape (1, n_features, n_classes)
    contributions = sv[0, :, class1_idx]
    baseline = float(explainer.expected_value[class1_idx])

    breakdown = {name: round(float(value) * 100, 1) for name, value in zip(FEATURE_NAMES, contributions)}
    breakdown["baseline"] = round(baseline * 100, 1)
    return proba_safe, breakdown


def score_candidate(features: FeatureVector, settings: Settings) -> TrustResult:
    """Blend of the always-available rule scorer and (once trained on enough
    *real* samples) the RandomForest+SHAP layer (DESIGN.md 6.5). Below
    min_training_samples -- including the common case where model.pkl
    doesn't exist yet at all -- the RF is ignored and the rule score is
    authoritative, unchanged from Phase 2's behavior.

    Gated on bundle.n_real_samples, not the synthetic+real total: the fixed
    synthetic dataset (app/ml/data/synthetic_examples.json) alone already
    clears the default min_training_samples=50, so gating on the total meant
    a single `python -m app.ml.train` run -- with zero real logged
    outcomes -- was enough to activate RF blending. The gate's actual intent
    is "don't trust the learned model until it's seen enough real-world
    signal"; the synthetic set exists to make the model *fittable* at all
    before any real data exists, not to count toward that trust bar.
    """
    rule_result = _score_rule(features, settings)

    bundle = _load_bundle()
    if bundle is None or bundle.n_real_samples < settings.min_training_samples:
        return rule_result

    proba_safe, shap_breakdown = _shap_breakdown(features, bundle)
    rf_score = 100 * proba_safe

    blended = round(settings.rf_blend_weight * rule_result.score + (1 - settings.rf_blend_weight) * rf_score, 2)
    blended = max(0.0, min(100.0, blended))

    return TrustResult(score=blended, breakdown=shap_breakdown, decision=_decide(blended, settings))
