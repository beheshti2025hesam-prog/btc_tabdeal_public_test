from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from forward.native_ohlcv_collector_v1 import NativeOHLCVCollectorV1


class FakeSource:
    def __init__(self, batch=None):
        self.batch = batch
        self.calls = []

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        if self.batch is None:
            raise ValueError("source rejected response")
        return self.batch


def batch():
    candle = SimpleNamespace(
        open_time_ms=1800000000000, close_time_ms=1800000899999,
        open=Decimal("100.00"), high=Decimal("102.00"),
        low=Decimal("99.00"), close=Decimal("101.25"),
        volume=Decimal("2.500"), quote_volume=Decimal("250.625"),
        trade_count=12, closed=True,
    )
    gap = SimpleNamespace(
        expected_open_time_ms=1800000900000,
        next_observed_open_time_ms=1800002700000,
        missing_intervals=2,
    )
    return SimpleNamespace(
        venue="binance", product="spot", symbol="BTCUSDT", interval="15m",
        endpoint_kind="uiKlines", fetched_at_ms=1800001800000,
        response_sha256="a" * 64, candles=(candle,), gaps=(gap,),
        open_candles_excluded=1,
    )


def test_disabled_collector_does_not_call_source_or_create_files(tmp_path):
    source = FakeSource(batch())
    path = tmp_path / "nested" / "batches.jsonl"
    collector = NativeOHLCVCollectorV1(source=source, output=path)
    with pytest.raises(RuntimeError, match="disabled"):
        collector.collect_once(symbol="BTCUSDT")
    assert source.calls == []
    assert not path.exists()


def test_enabled_collector_persists_native_batch_durably_and_losslessly(tmp_path):
    source = FakeSource(batch())
    path = tmp_path / "nested" / "batches.jsonl"
    collector = NativeOHLCVCollectorV1(source=source, output=path, enabled=True)
    result = collector.collect_once(symbol="BTCUSDT", interval="15m", limit=5, as_of_ms=1800001800000)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == result
    assert stored["artifact_type"] == "NATIVE_OHLCV_BATCH"
    assert stored["candles"][0]["open"] == "100.00"
    assert stored["candles"][0]["volume"] == "2.500"
    assert stored["response_sha256"] == "a" * 64
    assert stored["gaps"][0]["missing_intervals"] == 2
    assert stored["execution"] == "OFF"
    assert source.calls[0]["symbol"] == "BTCUSDT"
    assert path.stat().st_mode & 0o777 == 0o600


def test_failed_fetch_does_not_create_or_append_partial_record(tmp_path):
    source = FakeSource()
    path = tmp_path / "batches.jsonl"
    collector = NativeOHLCVCollectorV1(source=source, output=path, enabled=True)
    with pytest.raises(ValueError, match="rejected"):
        collector.collect_once(symbol="BTCUSDT")
    assert not path.exists()


def test_enabled_must_be_an_exact_boolean(tmp_path):
    with pytest.raises(ValueError, match="enabled must be bool"):
        NativeOHLCVCollectorV1(source=FakeSource(batch()), output=tmp_path / "x", enabled=1)


def test_incomplete_existing_jsonl_tail_fails_closed(tmp_path):
    source = FakeSource(batch())
    path = tmp_path / "batches.jsonl"
    path.write_bytes(b'{"artifact_type":"NATIVE_OHLCV_BATCH"')
    collector = NativeOHLCVCollectorV1(source=source, output=path, enabled=True)
    with pytest.raises(RuntimeError, match="incomplete trailing record"):
        collector.collect_once(symbol="BTCUSDT")
    assert path.read_bytes() == b'{"artifact_type":"NATIVE_OHLCV_BATCH"'
