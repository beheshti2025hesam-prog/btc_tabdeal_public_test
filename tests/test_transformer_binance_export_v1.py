from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from forward.native_ohlcv_v1 import INTERVAL_MS
from scripts import export_binance_ohlcv_for_transformer_v1 as exporter


def _candles(start_ms: int, count: int, interval: str = "15m"):
    step = INTERVAL_MS[interval]
    return [
        SimpleNamespace(
            open_time_ms=start_ms + i * step,
            close_time_ms=start_ms + (i + 1) * step - 1,
            open="100.0", high="101.0", low="99.0", close="100.5",
            volume="12.0",
        )
        for i in range(count)
    ]


class FakeSource:
    candles = []
    gap = False
    calls = 0

    def __init__(self):
        self.calls = 0

    def fetch(self, *, symbol, interval, limit, start_time_ms, end_time_ms, as_of_ms):
        self.calls += 1
        assert symbol == "BTCUSDT"
        assert interval == "15m"
        selected = [c for c in self.candles if start_time_ms <= c.open_time_ms <= end_time_ms]
        page = selected[:limit]
        return SimpleNamespace(
            response_sha256=hashlib.sha256(f"page-{self.calls}".encode()).hexdigest(),
            gaps=(object(),) if self.gap else (),
            candles=tuple(page),
        )


def test_exporter_paginates_and_writes_hash_locked_closed_candle_csv(tmp_path, monkeypatch):
    now_ms = 2_000_000_000_000
    start_ms = ((now_ms - 30 * 86_400_000) // INTERVAL_MS["15m"]) * INTERVAL_MS["15m"]
    FakeSource.candles = _candles(start_ms, 1600)
    FakeSource.gap = False
    instances = []

    def factory():
        instance = FakeSource()
        instances.append(instance)
        return instance

    monkeypatch.setattr(exporter, "BinanceUsdMPerpetualKlineSource", factory)
    csv_path = tmp_path / "candles.csv"
    manifest_path = tmp_path / "manifest.json"
    manifest = exporter.export_binance_ohlcv(
        output_csv=csv_path,
        manifest_path=manifest_path,
        days=30,
        interval="15m",
        now_ms=now_ms,
    )
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1600
    assert instances[0].calls == 2
    assert manifest["closed_candles"] == 1600
    assert manifest["request_count"] == 2
    assert manifest["dataset_csv_sha256"] == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert json.loads(manifest_path.read_text())["dataset_csv_sha256"] == manifest["dataset_csv_sha256"]
    assert rows[0]["timestamp"].endswith("+00:00")


def test_exporter_aborts_when_existing_adapter_reports_candle_gaps(tmp_path, monkeypatch):
    now_ms = 2_000_000_000_000
    start_ms = ((now_ms - 30 * 86_400_000) // INTERVAL_MS["15m"]) * INTERVAL_MS["15m"]
    FakeSource.candles = _candles(start_ms, 1000)
    FakeSource.gap = True
    monkeypatch.setattr(exporter, "BinanceUsdMPerpetualKlineSource", FakeSource)
    with pytest.raises(ValueError, match="source candle gaps"):
        exporter.export_binance_ohlcv(
            output_csv=tmp_path / "candles.csv",
            manifest_path=tmp_path / "manifest.json",
            days=30,
            interval="15m",
            now_ms=now_ms,
        )
    assert not (tmp_path / "candles.csv").exists()
