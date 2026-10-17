from datetime import datetime, timezone
import json

import pytest

from forward.wallex_rest_readonly_v1 import (
    WallexRestWindowCollectorV1,
    fetch_public_snapshot,
    normalize_rest_trade,
)


NOW = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)


def trade():
    return {
        "symbol": "BTCUSDT",
        "price": "62000.125",
        "quantity": "0.0012",
        "isBuyOrder": True,
        "timestamp": "2026-10-17T09:59:59Z",
    }


def test_normalizes_rest_trade_without_fabricating_sequence():
    record = normalize_rest_trade(trade(), received_at=NOW)
    assert record["venue"] == "wallex"
    assert record["sequence"] is None
    assert record["sequence_semantics"] == "NOT_DOCUMENTED_BY_VENUE"
    assert record["coverage"] == "LATEST_WINDOW_ONLY"
    assert record["side"] == "BUY"


def test_rejects_bad_timestamp_and_numeric_fields():
    bad = trade()
    bad["timestamp"] = "2026-10-17T09:00:00"
    with pytest.raises(ValueError):
        normalize_rest_trade(bad, received_at=NOW)
    bad = trade()
    bad["price"] = "NaN"
    with pytest.raises(ValueError):
        normalize_rest_trade(bad, received_at=NOW)


def test_collector_enforces_minimum_poll_interval(tmp_path):
    with pytest.raises(ValueError, match="at least 15"):
        WallexRestWindowCollectorV1(output=str(tmp_path / "events.jsonl"), interval_seconds=1)


def test_collector_is_disabled_by_default(tmp_path):
    collector = WallexRestWindowCollectorV1(output=str(tmp_path / "events.jsonl"))
    with pytest.raises(RuntimeError, match="disabled"):
        collector.run()


def test_collect_once_deduplicates_exact_payload_and_persists_jsonl(tmp_path):
    output = tmp_path / "events.jsonl"
    snapshot = {"latest_trades": [trade()], "trade_window_coverage": "LATEST_WINDOW_ONLY"}
    collector = WallexRestWindowCollectorV1(
        output=str(output), enabled=True, snapshot_provider=lambda: snapshot
    )
    assert collector.collect_once() == 1
    assert collector.collect_once() == 0
    lines = output.read_text().splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["symbol"] == "BTCUSDT"
    assert saved["sequence"] is None


def test_fetch_public_snapshot_validates_all_three_endpoints():
    responses = [
        {"success": True, "result": {"symbols": {"BTCUSDT": {"symbol": "BTCUSDT"}}}},
        {"success": True, "result": {"ask": [], "bid": []}},
        {"success": True, "result": {"latestTrades": [trade()]}},
    ]
    class Response:
        status = 200
        def __init__(self, payload):
            self.payload = json.dumps(payload).encode()
        def read(self, limit):
            return self.payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    def opener(request, timeout):
        return Response(responses.pop(0))
    snapshot = fetch_public_snapshot(opener=opener)
    assert snapshot["symbol"] == "BTCUSDT"
    assert len(snapshot["latest_trades"]) == 1
    assert snapshot["trade_window_coverage"] == "LATEST_WINDOW_ONLY"
