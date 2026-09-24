from datetime import datetime, timedelta, timezone

from core.data_engine.alignment import TimeframeAligner


class Snapshot:
    def __init__(self, timestamp):
        self.timestamp = timestamp


class History:
    def __init__(self, symbol, snapshots):
        self.symbol = symbol
        self.snapshots = tuple(snapshots)


def test_alignment_never_uses_future_snapshot():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = History("BTC_USDT", [Snapshot(t0), Snapshot(t0 + timedelta(minutes=15))])
    result = TimeframeAligner().align(
        target_timestamp=t0 + timedelta(minutes=10),
        histories=[history],
    )
    assert result.snapshots[0].timestamp == t0


def test_empty_history_is_allowed_but_returns_no_selected_snapshot():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = History("BTC_USDT", [])
    result = TimeframeAligner().align(target_timestamp=t0, histories=[history])
    assert result.snapshots == ()
