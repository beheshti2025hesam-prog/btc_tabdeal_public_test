from __future__ import annotations

import json
from pathlib import Path

import scripts.ops.hes_smart_storage_manager_v1 as storage
from forward.sealed_jsonl_segments_v1 import (
    inspect_jsonl_segments,
    logical_sha256,
    read_jsonl_records,
)


def _write_rows(path: Path, name: str, count: int = 7) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            handle.write(json.dumps({
                "event_id": f"{name}:{index}",
                "decision": "NO_TRADE",
                "payload": "x" * 256,
            }, sort_keys=True) + "\n")


def test_threshold_policy_seals_all_four_allowlisted_active_ledgers(tmp_path, monkeypatch):
    names = (
        "trade_journal_v2.jsonl",
        "observations_live_v1.jsonl",
        "global_market_candles_1m_v1.jsonl",
        "neutral_decision_outcomes_v1.jsonl",
    )
    paths = {name: tmp_path / "data" / "forward" / name for name in names}
    before_hashes = {}
    before_counts = {}
    for name, path in paths.items():
        _write_rows(path, name)
        before_hashes[name] = logical_sha256(path)
        before_counts[name] = len(read_jsonl_records(path))

    monkeypatch.setattr(storage, "ACTIVE_SEAL_POLICIES", {name: 1 for name in names})
    result = storage.apply_allowlisted_active_sealing(tmp_path)

    assert result["status"] == "POLICY_APPLIED"
    assert set(result["allowlist"]) == set(names)
    assert set(result["files"]) == set(names)
    for name, path in paths.items():
        item = result["files"][name]
        inventory = inspect_jsonl_segments(path, verify=True)
        assert item["status"] == "SEALED_AND_VERIFIED"
        assert inventory["verified"] is True
        assert inventory["record_count"] == before_counts[name]
        assert logical_sha256(path) == before_hashes[name]
        assert path.stat().st_size == 0


def test_threshold_policy_leaves_small_hot_tails_untouched(tmp_path, monkeypatch):
    names = tuple(storage.ACTIVE_SEAL_POLICIES)
    for name in names:
        _write_rows(tmp_path / "data" / "forward" / name, name, count=1)
    monkeypatch.setattr(storage, "ACTIVE_SEAL_POLICIES", {name: 10**9 for name in names})

    result = storage.apply_allowlisted_active_sealing(tmp_path)

    assert result["status"] == "POLICY_APPLIED"
    assert all(item["status"] == "BELOW_THRESHOLD" for item in result["files"].values())
    assert all(not (tmp_path / "data" / "forward" / (name + ".segments")).exists() for name in names)


def test_active_inventory_requires_full_segment_verification(tmp_path, monkeypatch):
    names = tuple(storage.ACTIVE_SEAL_POLICIES)
    for name in names:
        _write_rows(tmp_path / "data" / "forward" / name, name)
    monkeypatch.setattr(storage, "ACTIVE_SEAL_POLICIES", {name: 1 for name in names})
    storage.apply_allowlisted_active_sealing(tmp_path)

    import getpass
    report = storage.active_data_segment_inventory(
        tmp_path, verify=True, service_user=getpass.getuser()
    )

    assert report["status"] == "VERIFIED"
    assert report["verified"] is True
    assert report["segment_count"] == 4
    assert report["errors"] == []


def test_observation_writer_appends_after_existing_sealed_segment(tmp_path):
    from datetime import datetime, timezone
    from forward.forward_observation_writer_v1 import ForwardObservationWriterV1
    from forward.runtime_guard_v1 import RuntimeContext

    path = tmp_path / "data/forward/observations_live_v1.jsonl"
    writer = ForwardObservationWriterV1(path)
    context = RuntimeContext(
        source="compression_canary",
        observed_at=datetime.now(timezone.utc).isoformat(),
        forward_run_id="CANARY-FORWARD",
    )
    def row(suffix):
        return {
            "event_id": f"CANARY-FORWARD:{suffix}",
            "observed_at": context.observed_at,
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "status": "COMPRESSION_APPEND_CANARY",
            "source": "compression_canary",
            "outcome": None,
            "closed_at": None,
        }

    writer.append(row("before-seal"), context=context)
    writer.seal()
    writer.append(row("after-seal"), context=context)
    assert [x["event_id"] for x in writer.read()] == [
        "CANARY-FORWARD:before-seal", "CANARY-FORWARD:after-seal"
    ]


def test_neutral_outcome_writer_appends_after_existing_sealed_segment(tmp_path):
    from datetime import datetime, timezone, timedelta
    from forward.neutral_decision_outcomes_v1 import SCHEMA, run
    from forward.sealed_jsonl_segments_v1 import seal_hot_file, read_jsonl_records

    data = tmp_path / "data/forward"
    data.mkdir(parents=True)
    observed = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
    decision = {
        "event_id": "CANARY-NO-TRADE-001",
        "observed_at": observed.isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": "NO_TRADE",
        "evidence_source": "canary",
        "outcome": None,
        "closed_at": None,
    }
    (data / "trade_journal_v2.jsonl").write_text(json.dumps(decision) + "\n")
    candles = []
    start = observed - timedelta(minutes=15)
    for index in range(5):
        opened = start + timedelta(minutes=15 * index)
        closed = opened + timedelta(minutes=15)
        price = 100 + index
        candles.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "15m",
            "open_time": int(opened.timestamp()),
            "close_time": int(closed.timestamp()),
            "open": str(price),
            "high": str(price + 1),
            "low": str(price - 1),
            "close": str(price),
            "volume": "10",
            "closed": True,
        })
    (data / "global_market_candles_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candles)
    )
    output = data / "neutral_decision_outcomes_v1.jsonl"
    output.write_text(json.dumps({
        "schema": SCHEMA,
        "outcome_id": "seed-outcome",
        "decision_event_id": "seed-event",
        "horizon": "1h",
        "horizon_complete": True,
        "outcome_class": "SEED",
    }) + "\n")
    assert seal_hot_file(output) is not None

    run(tmp_path)
    rows = read_jsonl_records(output)
    appended = [row for row in rows if row.get("decision_event_id") == decision["event_id"]]
    assert len(appended) == 1
    assert output.stat().st_size > 0
