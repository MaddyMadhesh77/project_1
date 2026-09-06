from datetime import date

from app.services.analytics import build_trend


def _d(day: str) -> date:
    return date.fromisoformat(day)


def test_build_trend_buckets_decisions_by_calendar_date():
    decision_day_counts = [
        (_d("2026-07-28"), "store", 2),
        (_d("2026-07-28"), "review", 1),
        (_d("2026-07-29"), "reject", 1),
    ]
    trend = build_trend(decision_day_counts, [])

    assert [p.date for p in trend] == ["2026-07-28", "2026-07-29"]
    assert trend[0].store == 2
    assert trend[0].review == 1
    assert trend[0].reject == 0
    assert trend[1].reject == 1
    assert trend[1].store == 0


def test_build_trend_counts_rollbacks_on_their_own_date():
    decision_day_counts = [(_d("2026-07-28"), "store", 1)]
    rollback_day_counts = [(_d("2026-07-28"), 2), (_d("2026-07-30"), 1)]

    trend = build_trend(decision_day_counts, rollback_day_counts)

    by_date = {p.date: p for p in trend}
    assert by_date["2026-07-28"].rollbacks == 2
    assert by_date["2026-07-30"].rollbacks == 1
    assert by_date["2026-07-30"].store == 0


def test_build_trend_ignores_unknown_decision_values():
    decision_day_counts = [(_d("2026-07-28"), "store", 1), (_d("2026-07-28"), "admin_override", 5)]
    trend = build_trend(decision_day_counts, [])
    assert trend[0].store == 1
    assert trend[0].review == 0
    assert trend[0].reject == 0


def test_build_trend_empty_input_returns_empty_list():
    assert build_trend([], []) == []


def test_build_trend_sorted_ascending_regardless_of_input_order():
    decision_day_counts = [
        (_d("2026-08-01"), "store", 1),
        (_d("2026-07-28"), "store", 1),
        (_d("2026-07-30"), "reject", 1),
    ]
    trend = build_trend(decision_day_counts, [])
    assert [p.date for p in trend] == ["2026-07-28", "2026-07-30", "2026-08-01"]
