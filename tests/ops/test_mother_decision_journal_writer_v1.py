from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json

import pytest

from forward.forward_journal_v1 import ForwardJournalV1
from forward.trade_journal_view_v1 import read_decision_journal
from scripts.ops.mother_decision_journal_writer_v1 import (
    build_mother_journal_record,
    run_once,
)


def _mother():
    now = datetime.now(timezone.utc)
    return {
        "schema": "hes.mother_runtime_dashboard.v1",
        "runtime_mode": "LIVE_DATA_RUNTIME_SPECIALISTS",
        "status": "BLOCKED_RISK_VETO",
        "decision": "NO_TRADE",
        "reason_codes": ["AGENT_VETO:confirmation", "AGENT_VETO:risk"],
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "observed_at": now.isoformat(),
        "trace_id": "a" * 64,
        "audit_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "market_regime": "DOWNTREND",
        "market_data_provenance": {
            "source": "gateio_public_spot",
            "timeframes": {"15m": {"input_batch_sha256": "d" * 64}},
        },
        "strategy_proposal": {
            "decision": "NO_TRADE", "direction": "NONE",
            "policy_version": "test-policy-v1", "quality_score": 75,
            "reason_codes": ["NO_CONFIRMED_BREAKOUT"],
        },
        "strategy_family_paper_lane": {
            "status": "NO_CANDIDATE", "reason_codes": ["NO_FAMILY_CANDIDATE"],
            "selected_candidate": None,
        },
        "consensus": {
            "decision": "NO_TRADE", "direction": "UNKNOWN",
            "conflict_class": "MANDATORY_VETO",
            "reason_codes": ["AGENT_VETO:risk"],
        },
        "stages": [
            {"agent": "data_quality", "agent_version": "dq-v1", "state": "PASS", "reason_codes": [], "evidence_refs": ["market_batch:15m:sha256:" + "d" * 64]},
            {"agent": "market_structure", "agent_version": "ms-v1", "state": "PASS", "reason_codes": [], "evidence_refs": ["market_batch:15m:sha256:" + "d" * 64]},
            {"agent": "signal", "agent_version": "signal-v1", "state": "PASS", "reason_codes": ["NO_CONFIRMED_BREAKOUT"], "evidence_refs": ["market_batch:15m:sha256:" + "d" * 64]},
            {"agent": "confirmation", "agent_version": "confirmation-v1", "state": "UNCONFIRMED", "reason_codes": ["HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION"], "evidence_refs": ["news_snapshot_sha256:" + "e" * 64, "news_brief_sha256:" + "f" * 64, "news_context_sha256:" + "1" * 64]},
            {"agent": "risk", "agent_version": "risk-v1", "state": "REJECTED", "reason_codes": ["CONFIRMATION_NOT_VALID"], "evidence_refs": ["risk_sha256:" + "2" * 64]},
            {"agent": "decision", "agent_version": "decision-v1", "state": "DECIDED", "reason_codes": [], "evidence_refs": ["market_batch:15m:sha256:" + "d" * 64]},
            {"agent": "evaluation", "agent_version": "evaluation-v1", "state": "OBSERVED", "reason_codes": [], "evidence_refs": ["market_batch:15m:sha256:" + "d" * 64]},
        ],
        "news_context": {
            "snapshot_sha256": "e" * 64,
            "brief_sha256": "f" * 64,
            "context_sha256": "1" * 64,
            "status": "READY",
        },
        "witness": {
            "verified": True,
            "execution_authorized": False,
            "audit_sha256": "b" * 64,
            "trace_id": "a" * 64,
        },
        "execution_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
        "outcomes_inferred": False,
        "external_llm_used": False,
        "journal_write": False,
    }


def test_mother_no_trade_maps_to_canonical_append_only_event():
    row = build_mother_journal_record(_mother())
    assert row["schema"] == "hes_mother_decision_journal_event_v1"
    assert row["decision"] == "NO_TRADE"
    assert row["direction"] == "NONE"
    assert row["decision_gate"] == "CONFIRMATION"
    assert row["execution_enabled"] is False
    assert row["orders_placed"] is False
    assert row["outcome"] is None
    assert row["closed_at"] is None
    assert row["event_id"].startswith("hes-mother-")


def test_same_market_news_and_gate_evidence_is_idempotent(tmp_path):
    first = _mother()
    second = deepcopy(first)
    second["observed_at"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    second["trace_id"] = "9" * 64
    second["audit_sha256"] = "8" * 64
    second["witness"]["trace_id"] = second["trace_id"]
    second["witness"]["audit_sha256"] = second["audit_sha256"]
    second["stages"][3]["evidence_refs"][-1] = "news_context_sha256:" + "7" * 64
    a = build_mother_journal_record(first)
    b = build_mother_journal_record(second)
    assert a["event_id"] == b["event_id"]
    path = tmp_path / "journal.jsonl"
    assert ForwardJournalV1(path).append_event(a) is True
    assert ForwardJournalV1(path).append_event(b) is False
    assert len(path.read_text().splitlines()) == 1


def test_candidate_geometry_is_preserved_only_when_complete():
    mother = _mother()
    mother["strategy_family_paper_lane"]["selected_candidate"] = {
        "direction": "SHORT", "entry": 100, "stop_loss": 105, "take_profit": 90,
        "strategy_family_id": "range-family-v1",
        "strategy_family_version": "1.0.0",
    }
    row = build_mother_journal_record(mother)
    assert row["direction"] == "SHORT"
    assert row["proposal_direction"] == "SHORT"
    assert row["entry"] == 100.0
    assert row["stop_loss"] == 105.0
    assert row["take_profit"] == 90.0
    assert row["strategy_family_id"] == "range-family-v1"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"witness": {"verified": False, "execution_authorized": False}}, "MOTHER_WITNESS_NOT_VERIFIED"),
        ({"execution_enabled": True}, "MOTHER_SAFETY_BOUNDARY_VIOLATION:execution_enabled"),
        ({"orders_placed": True}, "MOTHER_SAFETY_BOUNDARY_VIOLATION:orders_placed"),
        ({"outcomes_inferred": True}, "MOTHER_SAFETY_BOUNDARY_VIOLATION:outcomes_inferred"),
        ({"journal_write": True}, "MOTHER_READ_API_MUST_REMAIN_READ_ONLY"),
        ({"source": "unknown"}, "MOTHER_MARKET_SCOPE_INVALID"),
        ({"decision": "BUY"}, "MOTHER_DECISION_INVALID"),
    ],
)
def test_invalid_or_unsafe_mother_payload_fails_closed(change, message):
    payload = _mother()
    payload.update(change)
    with pytest.raises(ValueError, match=message.replace(":", r"\:")):
        build_mother_journal_record(payload)


def test_run_once_appends_to_existing_journal_and_never_creates_orders(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    result = run_once(journal_path=path, mother_payload=_mother())
    assert result["status"] == "RECORDED"
    row = json.loads(path.read_text())
    assert row["service_name"] == "mother_runtime_decision_journal_writer"
    assert row["execution_enabled"] is False
    assert row["orders_placed"] is False
    assert row["outcome"] is None



def test_mother_event_is_visible_in_existing_decision_journal_projection(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    result = run_once(journal_path=path, mother_payload=_mother())
    projection = read_decision_journal(
        path, limit=20, matured_verification_path=tmp_path / "matured.jsonl"
    )
    assert result["status"] == "RECORDED"
    assert projection["status"] == "VERIFIED"
    assert projection["decision_count"] == 1
    assert projection["events"][0]["event_id"] == result["event_id"]
    assert projection["events"][0]["source"] == "gateio_public_spot"
    assert projection["events"][0]["decision"] == "NO_TRADE"
    assert projection["events"][0]["decision_origin"] == "MOTHER"
    assert projection["events"][0]["service_name"] == "mother_runtime_decision_journal_writer"


def test_writer_does_not_require_directory_creation_when_parent_already_exists(tmp_path, monkeypatch):
    path = tmp_path / "journal.jsonl"
    row = build_mother_journal_record(_mother())

    def deny_mkdir(*args, **kwargs):
        raise PermissionError("directory is intentionally read-only")

    monkeypatch.setattr(type(tmp_path), "mkdir", deny_mkdir)
    assert ForwardJournalV1(path).append_event(row) is True
    assert path.is_file()
