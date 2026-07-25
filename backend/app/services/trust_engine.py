from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.features import FeatureVector

# Additive rule-scorer weights (DESIGN.md 6.5 part 1). Hand-tuned constants --
# this is the "always available, no training data needed" layer; Phase 7 adds
# a RandomForest+SHAP layer blended on top of this, gated by min_training_samples.
_SOURCE_WEIGHT = 30.0
_SIMILARITY_WEIGHT = 24.0
_NOVELTY_BONUS = 24.0  # awarded instead of semantic_similarity when nothing existing was matched
_CONTEXT_WEIGHT = 18.0
_CONTRADICTION_WEIGHT = 40.0
_CORROBORATION_PER_MATCH = 10.0
_CORROBORATION_CAP = 20.0


@dataclass
class TrustResult:
    score: float
    breakdown: dict[str, float]
    decision: str  # store | review | reject


def score_candidate(features: FeatureVector, settings: Settings) -> TrustResult:
    """Deterministic additive rule scorer producing the trust_breakdown JSON
    shown in the dashboard (DESIGN.md 6.5's `source +30 / semantic_similarity
    +24 / ...` example). Pure function of the feature vector + configured
    thresholds -- no DB access, so this is the easiest place to unit test the
    scoring math and threshold branching in isolation.
    """
    source = round(_SOURCE_WEIGHT * features.source_reliability, 1)
    semantic_similarity = round(_SIMILARITY_WEIGHT * features.similarity, 1) if features.has_match else 0.0
    novelty = 0.0 if features.has_match else _NOVELTY_BONUS
    context = round(_CONTEXT_WEIGHT * features.conversation_recency, 1)

    if features.has_match and features.contradiction > 0:
        # Older/more-trusted memories require stronger evidence to overturn
        # (DESIGN.md 6.4) -- scale the penalty by how trusted the thing being
        # contradicted currently is.
        trust_weight = 0.5 + 0.5 * (features.prior_trust_score / 100)
        contradiction = round(-_CONTRADICTION_WEIGHT * features.contradiction * trust_weight, 1)
    else:
        contradiction = 0.0

    # A consistent restatement of the matched memory (no contradiction) is
    # itself a corroborating signal, on top of any other independent memories
    # already counted in corroboration_count -- otherwise a plain, uncontested
    # reaffirmation of an existing fact would score *below* a brand-new one
    # (which gets the novelty bonus instead), which has it backwards.
    self_corroboration = 1 if features.has_match and features.contradiction == 0 else 0
    corroboration = round(
        min(_CORROBORATION_CAP, (features.corroboration_count + self_corroboration) * _CORROBORATION_PER_MATCH), 1
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

    if total >= settings.trust_threshold_store:
        decision = "store"
    elif total >= settings.trust_threshold_review:
        decision = "review"
    else:
        decision = "reject"

    return TrustResult(score=round(total, 2), breakdown=breakdown, decision=decision)
