from types import SimpleNamespace
from decimal import Decimal

import forward.global_market_data_gateio_v1 as collector


def _candle(open_ms):
    return SimpleNamespace(
        open_time_ms=open_ms,
        close_time_ms=open_ms + 60_000 - 1,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
        close=Decimal("100.5"), volume=Decimal("2"),
        quote_volume=Decimal("200"), closed=True,
    )


def test_one_minute_retention_covers_24h_plus_recovery_margin():
    assert collector.persisted_candle_limit("1m") == 1500
    assert collector.persisted_candle_limit("15m") == 500
    assert collector.persisted_candle_limit("1h") == 500
    assert collector.persisted_candle_limit("4h") == 500


def test_gateio_1m_rest_fetch_paginates_to_1500_contiguous_bars(monkeypatch):
    monkeypatch.setattr(collector, "INTERVAL", "1m")
    monkeypatch.setattr(collector, "INTERVAL_SECONDS", 60)
    monkeypatch.setattr(collector, "MAX_PERSISTED_CANDLES", 1500)

    older = tuple(_candle(i * 60_000) for i in range(500))
    newest = tuple(_candle(i * 60_000) for i in range(500, 1500))

    class FakeSource:
        def __init__(self):
            self.calls = []

        def fetch(self, **kwargs):
            self.calls.append(kwargs)
            candles = newest if kwargs["limit"] == 1000 else older
            return SimpleNamespace(candles=candles, gaps=(), fetched_at_ms=1_800_100_000_000)

    source = FakeSource()
    rows = collector.fetch_recent_closed(source, now=1_800_100_000)

    assert len(rows) == 1500
    assert rows[0]["open_time"] == 0
    assert rows[-1]["open_time"] == 1499 * 60
    assert [call["limit"] for call in source.calls] == [1000, 500]
    assert source.calls[1]["end_time_ms"] == 500 * 60_000 - 1
