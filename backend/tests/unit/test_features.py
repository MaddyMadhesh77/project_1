import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.services.features import _conversation_recency, recency_from_gap


def test_recency_is_full_within_the_full_window():
    assert recency_from_gap(0, full_window=300, floor_window=86400, floor=0.3) == 1.0
    assert recency_from_gap(300, full_window=300, floor_window=86400, floor=0.3) == 1.0


def test_recency_hits_floor_at_or_past_the_floor_window():
    assert recency_from_gap(86400, full_window=300, floor_window=86400, floor=0.3) == 0.3
    assert recency_from_gap(999999, full_window=300, floor_window=86400, floor=0.3) == 0.3


def test_recency_decays_monotonically_between_the_windows():
    kwargs = dict(full_window=300, floor_window=86400, floor=0.3)
    midpoint = recency_from_gap(300 + (86400 - 300) / 2, **kwargs)
    assert 0.3 < midpoint < 1.0
    earlier = recency_from_gap(1000, **kwargs)
    later = recency_from_gap(50000, **kwargs)
    assert 1.0 > earlier > later > 0.3


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, value):
        self._value = value

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._value)


async def test_conversation_recency_is_full_for_a_brand_new_conversation():
    db = _FakeSession(None)  # no prior activity found
    settings = Settings()

    recency = await _conversation_recency(db, conversation_id=uuid.uuid4(), settings=settings)

    assert recency == 1.0


async def test_conversation_recency_decays_for_a_stale_conversation():
    stale_activity = datetime.now(timezone.utc) - timedelta(days=2)
    db = _FakeSession(stale_activity)
    settings = Settings()

    recency = await _conversation_recency(db, conversation_id=uuid.uuid4(), settings=settings)

    assert recency == settings.conversation_recency_floor
