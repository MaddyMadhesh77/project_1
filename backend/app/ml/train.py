"""app/ml/train.py -- Phase 7 (DESIGN.md 6.5 part 2, PLAN.md Phase 7).

Trains a RandomForestClassifier on:
  1. The hand-authored synthetic dataset (app/ml/data/synthetic_examples.json)
     -- always available, no DB needed. Covers the safe/poisoned cases
     DESIGN.md 6.5 calls for: paraphrases/corrections/corroborations vs.
     direct contradictions injected with low corroboration.
  2. Real logged outcomes from trust_events + rollback_events, when
     reachable -- a rollback's kept/reverted/removed verdict on a version
     retroactively labels that version's ORIGINAL trust_event as safe/
     poisoned (DESIGN.md 6.5: "rollback triggered = retroactive 'poisoned'
     label"). Best-effort: training never requires a live Postgres.

Serializes the trained model + metadata to app/ml/model.pkl (gitignored --
regenerate locally by running this script). services/trust_engine.py loads
this file if present and only lets it influence scoring once its recorded
`n_samples` clears Settings.min_training_samples; until this script has been
run at least once, scoring is 100% the Phase 2 rule engine -- cold start,
always demoable.

This is also the "documented/manual retrain trigger" PLAN.md Phase 7 asks
for at minimum: re-run this after enough real trust_events/rollback_events
have accumulated to fold that outcome data back into the model. There is
deliberately no automatic retrain loop (PLAN.md calls that optional polish).

Usage (from backend/, venv active): python -m app.ml.train
"""
from __future__ import annotations

import asyncio
import json
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier

from app.core.config import get_settings
from app.services import model_integrity
from app.services.features import FEATURE_NAMES

_DATA_PATH = Path(__file__).resolve().parent / "data" / "synthetic_examples.json"
_MODEL_PATH = Path(__file__).resolve().parent / "model.pkl"

_LABEL_TO_INT = {"safe": 1, "poisoned": 0}

Example = tuple[list[float], int]


def _load_synthetic() -> list[Example]:
    examples = json.loads(_DATA_PATH.read_text())
    return [
        ([float(ex["features"][name]) for name in FEATURE_NAMES], _LABEL_TO_INT[ex["label"]]) for ex in examples
    ]


async def _load_real_examples() -> list[Example]:
    """Real logged outcomes, when the DB is reachable. Best-effort: any
    connection failure just means training falls back to synthetic-only
    data, consistent with "every phase must leave the demo runnable" --
    training shouldn't require docker-compose to be up.
    """
    try:
        import sqlalchemy as sa

        from app.db.session import async_session_factory
        from app.models import RollbackOutcome, TrustEvent
    except Exception as exc:  # pragma: no cover -- import-time failure only
        print(f"  (skipping real logged data -- import failed: {exc})")
        return []

    try:
        async with async_session_factory() as db:
            outcome_rows = (
                await db.execute(sa.select(RollbackOutcome.version_id, RollbackOutcome.outcome))
            ).all()
            # kept => the rollback re-confirmed this version was fine despite
            # its poisoned ancestor => safe (1). reverted/removed => it didn't
            # survive re-validation => poisoned (0).
            label_by_version_id: dict[uuid.UUID, int] = {
                version_id: (1 if outcome == "kept" else 0) for version_id, outcome in outcome_rows
            }

            if not label_by_version_id:
                return []

            trust_event_rows = (
                await db.execute(
                    sa.select(TrustEvent)
                    .where(TrustEvent.version_id.in_(list(label_by_version_id)))
                    .where(TrustEvent.event_type.in_(["created", "updated"]))
                )
            ).scalars().all()
    except Exception as exc:
        print(f"  (skipping real logged data -- DB unreachable: {exc})")
        return []

    examples: list[Example] = []
    for te in trust_event_rows:
        raw_features = (te.details or {}).get("features")
        if not raw_features:
            continue
        label = label_by_version_id.get(te.version_id)
        if label is None:
            continue
        examples.append(([float(raw_features[name]) for name in FEATURE_NAMES], label))
    return examples


async def run_training() -> dict:
    """The actual training run, factored out of main() so
    app/api/routes/trust.py's POST /trust/retrain (bugs.md #10: "no endpoint
    ... to trigger retraining") can call it in-process instead of shelling
    out to `python -m app.ml.train`. Returns a JSON-able summary instead of
    printing -- main() below does the printing for the CLI entry point.
    """
    synthetic = _load_synthetic()
    real = await _load_real_examples()
    all_examples = synthetic + real

    X = [row for row, _ in all_examples]
    y = [label for _, label in all_examples]

    # max_depth caps overfitting on a dataset this small (a handful of
    # deep trees would just memorize individual points); n_estimators=200
    # keeps SHAP's per-tree averaging stable; random_state pins this to a
    # reproducible model, matching this project's other deterministic seeds
    # (scripts/seed_demo.py's fixed conversation_id, the RRF constant, etc).
    model = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, class_weight="balanced")
    model.fit(X, y)
    train_accuracy = model.score(X, y)

    trained_at = datetime.now(timezone.utc).isoformat()
    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "n_samples": len(all_examples),
        # Real logged examples only, distinct from n_samples -- what
        # Settings.min_training_samples gates RF activation on (see
        # trust_engine.score_candidate). The synthetic set makes the model
        # fittable before any real data exists; it doesn't count as evidence
        # the model has seen real-world signal.
        "n_real_samples": len(real),
        "trained_at": trained_at,
    }
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)

    signing_key = get_settings().model_signing_key
    signed = bool(signing_key)
    if signing_key:
        model_integrity.write_signature(_MODEL_PATH, signing_key)
    else:
        # Remove any stale signature from a previous signed run -- an old
        # .sig sitting next to a newly-retrained, now-unsigned model.pkl
        # would just fail verification instead of being treated as "unsigned".
        model_integrity.remove_signature(_MODEL_PATH)

    # trust_engine caches model.pkl for the process lifetime (see
    # services/trust_engine.py::_load_bundle) -- without this, a retrain
    # triggered via the API would write a new file that scoring keeps
    # ignoring until the server restarts.
    from app.services import trust_engine

    trust_engine.clear_model_cache()

    return {
        "n_samples": len(all_examples),
        "n_synthetic_samples": len(synthetic),
        "n_real_samples": len(real),
        "n_safe": sum(y),
        "n_poisoned": len(all_examples) - sum(y),
        "train_accuracy": round(train_accuracy, 3),
        "trained_at": trained_at,
        "signed": signed,
    }


async def main() -> None:
    summary = await run_training()

    if summary["signed"]:
        print(f"Signed {_MODEL_PATH}.sig (MODEL_SIGNING_KEY set)")
    else:
        print("MODEL_SIGNING_KEY not set -- saved model.pkl unsigned (services/trust_engine.py will load it "
              "without integrity verification and log a warning).")

    print(
        f"Trained on {summary['n_samples']} examples ({summary['n_synthetic_samples']} synthetic + "
        f"{summary['n_real_samples']} real logged) -- {summary['n_safe']} safe / {summary['n_poisoned']} poisoned. "
        f"Train accuracy: {summary['train_accuracy']:.3f}."
    )
    print(f"Saved to {_MODEL_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
