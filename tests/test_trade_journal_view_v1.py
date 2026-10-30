from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.trade_journal_view_v1 import JournalProjectionError, read_decision_journal


def write_signal(path, *, observed_at=None):
    return record_signal_decision(
        path,
        decision="NO_TRADE",
        observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        symbol="BTCUSDT",
        timeframe="15m",
        source="gateio_native_ohlcv_v1",
        product="spot",
        response_sha256="a" * 64,
        htf_response_sha256="b" * 64,
        strategy_evidence_sha256="c" * 64,
        policy_version="hes-strategy-policy-v1",
        status="BLOCKED",
        market_regime="UNKNOWN",
        rejected_at="RISK",
        reason_codes=["RISK_CONTEXT_UNKNOWN"],
        risk_state="RISK_REJECTED",
    )


def test_projects_canonical_signal_and_paper_decisions_without_inventing_outcomes(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "schema": "hes_trade_journal_paper_candidate_v1",
            "event_id": "paper-candidate-1", "observed_at": datetime.now(timezone.utc).isoformat(),
            "symbol": "BTCUSDT", "timeframe": "15m", "decision": "PAPER_CANDIDATE",
            "outcome": None, "execution_enabled": False, "orders_placed": False,
        }) + "\n")
    result = read_decision_journal(path)
    assert result["status"] == "VERIFIED"
    assert result["count"] == 2
    assert result["decision_count"] == 1
    event = result["events"][0]
    assert event["decision"] == "NO_TRADE"
    assert event["realized_outcome"] == "NOT_LINKED"
    assert event["execution"] == "OFF"
    assert event["reason_codes"] == ["RISK_CONTEXT_UNKNOWN"]


def test_rejects_tampered_json_and_duplicate_event_identity(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    line = path.read_text()
    path.write_text(line + line)
    with pytest.raises(JournalProjectionError, match="duplicate_event"):
        read_decision_journal(path)


def test_rejects_partial_trailing_record(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(JournalProjectionError, match="partial_trailing_record"):
        read_decision_journal(path)


def test_rejects_naive_timestamp(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    record = json.loads(path.read_text().strip())
    record["observed_at"] = "2026-10-25T10:00:00"
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(JournalProjectionError, match="naive_timestamp"):
        read_decision_journal(path)


def test_rejects_outcome_leakage_in_decision_record(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    record = json.loads(path.read_text().strip())
    record["outcome"] = "WIN"
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(JournalProjectionError, match="outcome_leakage"):
        read_decision_journal(path)


def test_rejects_invalid_limit(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with pytest.raises(JournalProjectionError, match="invalid_limit"):
        read_decision_journal(path, limit=0)
