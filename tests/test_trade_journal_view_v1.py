from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.trade_journal_view_v1 import JournalProjectionError, read_decision_journal


def write_event(path, *, observed_at=None):
    now = observed_at or datetime.now(timezone.utc).isoformat()
    return record_signal_decision(
        path,
        decision="NO_TRADE",
        observed_at=now,
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_native_ohlcv_v1",
        product="spot",
        response_sha256="a" * 64,
        htf_response_sha256="b" * 64,
        strategy_evidence_sha256="c" * 64,
        policy_version="hes-strategy-policy-v1",
        status="BLOCKED",
        market_regime="UNKNOWN",
        rejected_at="RISK",
        reason_codes=["RISK_CONTEXT_UNKNOWN"],
    )


def test_projects_verified_forward_decision_without_inventing_outcome(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    result = read_decision_journal(path)
    assert result["status"] == "VERIFIED"
    assert result["count"] == 1
    event = result["events"][0]
    assert event["decision"] == "NO_TRADE"
    assert event["realized_outcome"] == "NOT_LINKED"
    assert event["execution"] == "OFF"
    assert event["reason_codes"] == ["RISK_CONTEXT_UNKNOWN"]


def test_rejects_tampered_record(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    record = json.loads(path.read_text().strip())
    record["decision"] = "LONG"
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n")
    with pytest.raises(JournalProjectionError, match="digest_mismatch"):
        read_decision_journal(path)


def test_rejects_partial_trailing_record(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(JournalProjectionError, match="partial_trailing_record"):
        read_decision_journal(path)


def test_rejects_duplicate_event_identity(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    line = path.read_text()
    path.write_text(line + line)
    with pytest.raises(JournalProjectionError, match="duplicate_event"):
        read_decision_journal(path)


def test_rejects_naive_timestamp(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path, observed_at="2026-10-25T10:00:00")
    with pytest.raises(JournalProjectionError, match="naive_timestamp"):
        read_decision_journal(path)


def test_rejects_future_timestamp(tmp_path):
    path = tmp_path / "decision.jsonl"
    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    write_event(path, observed_at=future)
    with pytest.raises(JournalProjectionError, match="future_timestamp"):
        read_decision_journal(path)


def test_rejects_outcome_leakage_in_decision_log(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    record = json.loads(path.read_text().strip())
    record.pop("digest")
    record["outcome"] = "WIN"
    from forward.forward_observation_writer_v1 import observation_digest
    record["digest"] = observation_digest(record)
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(JournalProjectionError, match="outcome_leakage"):
        read_decision_journal(path)


def test_rejects_invalid_limit(tmp_path):
    path = tmp_path / "decision.jsonl"
    write_event(path)
    with pytest.raises(JournalProjectionError, match="invalid_limit"):
        read_decision_journal(path, limit=0)
