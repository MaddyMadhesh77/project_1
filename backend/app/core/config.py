from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root is one level above backend/
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://recovermem:recovermem@localhost:5432/recovermem"
    )

    # SQLAlchemy's async engine defaults to a 5-connection pool + 10 overflow,
    # sized for a toy app rather than anything under concurrent load -- every
    # request holds a connection for its whole lifetime (get_db's `async with
    # async_session_factory()`), so a handful of concurrent /chat requests
    # alone can exhaust the default pool and start queuing. Raised here to a
    # size that comfortably covers this app's request-scoped-session pattern;
    # tune via env for the target deployment's actual concurrency.
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    anthropic_api_key: str | None = None

    # Local/demo mode by default -- mirrors the Django/Flask DEBUG convention.
    # Gates things that are convenient for a solo demo but dangerous exposed
    # on a network: the attack-simulator endpoints (app/api/routes/attack.py)
    # are only registered when debug=True, and api_key is only optional when
    # debug=True (see app/core/security.py / create_app()). Set DEBUG=false
    # for any deployment reachable by anyone other than the operator.
    debug: bool = True

    # Shared-secret API key every request (other than /health) must present
    # via the X-API-Key header (app/core/security.py). Optional while
    # debug=True (today's zero-config local demo keeps working unauthenticated,
    # with a startup warning); required while debug=False -- the app refuses
    # to start without one rather than silently serving the attack/rollback/
    # chat endpoints to anyone on the network.
    api_key: str | None = None

    # Requests allowed per client (by API key, else by IP) per
    # rate_limit_window_seconds, enforced by app/core/rate_limit.py on every
    # route except /health. /chat is the expensive path (embedding + LLM call
    # + several DB writes per request) this most needs to bound, but the
    # limiter applies uniformly rather than trying to price each route.
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # HMAC key used to sign/verify app/ml/model.pkl before it's unpickled
    # (services/model_integrity.py). Unset -> model.pkl loads unverified, with
    # a loud warning (today's zero-config demo behavior); set it to make a
    # tampered/replaced model.pkl fail closed instead of silently executing
    # whatever the attacker pickled.
    model_signing_key: str | None = None

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Trust decision thresholds (0-100). >=store -> trusted, >=review -> low-trust/review,
    # below review -> reject/quarantine. Configurable so a demo can be tuned live.
    trust_threshold_store: float = 70.0
    trust_threshold_review: float = 40.0

    # Rule-scorer additive weights (services/trust_engine._score_rule,
    # DESIGN.md 6.5 part 1) -- hand-tuned constants, not calibrated against
    # labeled data (there isn't any yet; that's what Phase 7's RF+SHAP layer
    # is for once min_training_samples of *real* signal exists). Moved here
    # from module constants so they're tunable without a code change, same as
    # every other threshold in this file. Relative sizing, for whoever tunes
    # these next:
    #   - contradiction (40) is the largest weight on purpose: a hard
    #     contradiction, at full trust_weight, must be able to outweigh
    #     source + semantic_similarity + context combined (30+24+18=72) and
    #     still pull a well-supported-looking claim down toward review/reject.
    #   - source (30) is the strongest *positive* signal -- it's the only one
    #     available before any retrieval/matching happens at all.
    #   - similarity and novelty_bonus (24 each) are mutually exclusive (a
    #     candidate either matched something or didn't) and deliberately
    #     equal, so a genuinely new fact and a well-corroborated update land
    #     on comparable footing rather than one structurally outscoring the
    #     other.
    #   - context (18) is the smallest positive weight: conversation recency
    #     is the least decisive of the positive-evidence terms.
    #   - corroboration_per_match (10) is capped at corroboration_cap (20,
    #     i.e. 2 independent matches) so corroboration volume alone can't
    #     fully offset a hard contradiction or a low-reliability source --
    #     it's supporting evidence, not a trump card.
    # None of this is a substitute for what a per-claim-content risk model
    # (e.g. "I work at CERN" vs "I live in London" from the same source
    # currently scoring identically) would need -- that's a distinct feature
    # dimension (claim-domain/stakes classification), not a weight-tuning fix.
    trust_weight_source: float = 30.0
    trust_weight_similarity: float = 24.0
    trust_weight_novelty_bonus: float = 24.0
    trust_weight_context: float = 18.0
    trust_weight_contradiction: float = 40.0
    trust_weight_corroboration_per_match: float = 10.0
    trust_weight_corroboration_cap: float = 20.0

    # Retrieval / ML config, added here in Phase 0 so later phases don't hardcode values.
    retrieval_top_k: int = 5
    # Minimum REAL (non-synthetic) logged training examples app/ml/model.pkl
    # must have before the RandomForest+SHAP layer is allowed to influence
    # trust_score at all (gates on ModelBundle.n_real_samples, not the
    # synthetic+real total -- see trust_engine.score_candidate). The fixed
    # synthetic bootstrap set (app/ml/data/synthetic_examples.json) alone
    # clears this by count, but doesn't count toward it: it exists to make
    # the model fittable before any real data exists, not as evidence of
    # real-world signal.
    min_training_samples: int = 50

    # conversation_recency feature (services/features.py): 1.0 while a
    # conversation's gap-since-last-stored-memory is within
    # *_full_window_seconds, decaying linearly to *_floor once the gap
    # reaches *_floor_window_seconds. Hand-tuned, like the rule scorer's
    # weights below -- no labeled data yet to calibrate a "correct" decay
    # curve against.
    conversation_recency_full_window_seconds: int = 300  # 5 min: still live
    conversation_recency_floor_window_seconds: int = 86400  # 24h: fully stale
    conversation_recency_floor: float = 0.3

    # Phase 7: weight given to the rule scorer's own score when blending with
    # the RandomForest's 100*P(safe) once the model has cleared
    # min_training_samples. 0.5 = equal weight. Below the sample gate, the RF
    # is ignored entirely and this weight doesn't apply (rule score alone).
    rf_blend_weight: float = 0.5

    # Cosine-similarity floor for treating a retrieval hit as "the same memory,
    # being updated" rather than an unrelated fact (Phase 2, DESIGN.md 6.3/6.6).
    retrieval_same_memory_threshold: float = 0.5

    # Cosine-similarity floor for treating a retrieval hit (that did NOT clear
    # retrieval_same_memory_threshold, so it's a genuinely different memory)
    # as "supporting context" worth recording a dependency_edges row for
    # (Phase 4, DESIGN.md 6.9) -- below this, a hit is too weakly related to
    # count as a derivation link.
    dependency_edge_similarity_threshold: float = 0.3

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
