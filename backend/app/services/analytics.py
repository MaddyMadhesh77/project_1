from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryVersion, RollbackEvent, TrustEvent

# MemoryVersion.decision values (DESIGN.md 6.5) -- the only three the trend
# chart buckets; anything else (there isn't anything else today) is ignored
# rather than raising, so a future decision value doesn't break the endpoint.
DECISIONS = ("store", "review", "reject")


@dataclass
class TrendPoint:
    date: str
    store: int
    review: int
    reject: int
    rollbacks: int


def build_trend(
    decision_day_counts: list[tuple[date, str, int]],
    rollback_day_counts: list[tuple[date, int]],
) -> list[TrendPoint]:
    """Merges pre-aggregated (day, decision, count) and (day, count) rollback
    rows into one TrendPoint per calendar date, ascending. Split out from
    get_summary as a pure function -- the only non-trivial logic in
    /analytics/summary -- so it's unit-testable without a database, matching
    this codebase's convention (trust_engine, graph, merkle, rollback) of
    keeping the actual decision logic DB-free.

    Takes already-aggregated counts, not raw per-row (created_at, decision)
    tuples: get_summary does the GROUP BY date_trunc('day', created_at),
    decision in SQL, not by loading every version row into Python and
    bucketing them here -- that was O(total versions) per call regardless of
    how many distinct days/decisions the result actually has.
    """
    buckets: dict[date, dict[str, int]] = defaultdict(
        lambda: {"store": 0, "review": 0, "reject": 0, "rollbacks": 0}
    )

    for day, decision, count in decision_day_counts:
        if decision in DECISIONS:
            buckets[day][decision] += count

    for day, count in rollback_day_counts:
        buckets[day]["rollbacks"] += count

    return [
        TrendPoint(date=day.isoformat(), store=b["store"], review=b["review"], reject=b["reject"], rollbacks=b["rollbacks"])
        for day, b in sorted(buckets.items())
    ]


# Trust-gate decisions only: versions the trust engine actually scored on the
# way in (chat, demo seed), identified by their created/updated trust event.
# Counting every memory_versions row also counted the 1-3 versions each
# rollback writes and attack-simulator injections, so a single rollback showed
# up as extra "store"/"reject" decisions on the trend chart. Rollbacks are
# counted separately (rollback_count / the trend's rollbacks series).
_GATE_EVENT_TYPES = ("created", "updated")
_gate_scored = MemoryVersion.version_id.in_(
    sa.select(TrustEvent.version_id).where(TrustEvent.event_type.in_(_GATE_EVENT_TYPES))
)


async def get_summary(db: AsyncSession) -> dict:
    status_rows = (await db.execute(sa.select(Memory.status, sa.func.count()).group_by(Memory.status))).all()
    decision_rows = (
        await db.execute(
            sa.select(MemoryVersion.decision, sa.func.count()).where(_gate_scored).group_by(MemoryVersion.decision)
        )
    ).all()

    total_memories = (await db.execute(sa.select(sa.func.count()).select_from(Memory))).scalar_one()
    total_versions = (await db.execute(sa.select(sa.func.count()).select_from(MemoryVersion))).scalar_one()
    rollback_count = (await db.execute(sa.select(sa.func.count()).select_from(RollbackEvent))).scalar_one()

    # Aggregated in SQL (GROUP BY the calendar date, decision) instead of
    # pulling every version/rollback row into Python to bucket by hand --
    # this used to be O(total versions) transferred and processed per call
    # regardless of how few distinct (day, decision) buckets the trend chart
    # actually needs.
    version_day = sa.cast(sa.func.date_trunc("day", MemoryVersion.created_at), sa.Date).label("day")
    decision_day_rows = (
        await db.execute(
            sa.select(version_day, MemoryVersion.decision, sa.func.count().label("n"))
            .where(_gate_scored)
            .group_by(version_day, MemoryVersion.decision)
        )
    ).all()

    rollback_day = sa.cast(sa.func.date_trunc("day", RollbackEvent.started_at), sa.Date).label("day")
    rollback_day_rows = (
        await db.execute(sa.select(rollback_day, sa.func.count().label("n")).group_by(rollback_day))
    ).all()

    trend = build_trend(
        [(r.day, r.decision, r.n) for r in decision_day_rows],
        [(r.day, r.n) for r in rollback_day_rows],
    )

    return {
        "status_counts": {status: count for status, count in status_rows},
        "decision_counts": {decision: count for decision, count in decision_rows},
        "total_memories": total_memories,
        "total_versions": total_versions,
        "rollback_count": rollback_count,
        "trend": [asdict(point) for point in trend],
    }
