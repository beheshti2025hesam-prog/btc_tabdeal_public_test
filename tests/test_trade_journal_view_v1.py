from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
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


def test_optional_canonical_identity_and_execution_contract(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with pytest.raises(JournalProjectionError, match="unexpected_source"):
        read_decision_journal(path, expected_source="gateio_public_spot")
def test_rejects_invalid_limit(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with pytest.raises(JournalProjectionError, match="invalid_limit"):
        read_decision_journal(path, limit=0)



def _write_v2_decision(path, *, proposal_decision="NO_TRADE", confirmation_state="UNCONFIRMED",
                       risk_state="RISK_REJECTED", final_decision="NO_TRADE"):
    route = {
        "family_id": "trend_breakout",
        "family_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
        "activation_state": "CANDIDATE_LOCKED_NOT_ACTIVE",
    }
    evidence = {
        "confirmation": {
            "state": confirmation_state,
            "reason_codes": ["REQUIRED_CHECK_FAILED"] if confirmation_state == "UNCONFIRMED" else [],
            "checks": [{"name": "direction_regime_alignment", "state": "FAIL" if confirmation_state == "UNCONFIRMED" else "PASS"}],
        },
        "risk": {
            "state": risk_state,
            "reason_codes": ["CONFIRMATION_NOT_VALID"] if risk_state == "RISK_REJECTED" else [],
            "checks": [{"name": "confirmation_valid", "state": "FAIL" if risk_state == "RISK_REJECTED" else "PASS"}],
        },
        "market_data_provenance": {
            "timeframes": {"15m": {"input_batch_sha256": "a" * 64}, "1h": {"input_batch_sha256": "b" * 64}},
        },
    }
    record = {
        "event_id": "hes-v2-attribution-test",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": final_decision,
        "direction": "NONE",
        "signal_state": proposal_decision,
        "proposal_decision": proposal_decision,
        "proposal_reasons": ["NO_CONFIRMED_20_BAR_BREAKOUT"] if proposal_decision == "NO_TRADE" else [],
        "confirmation_state": confirmation_state,
        "risk_state": risk_state,
        "no_trade_reason": "NO_CONFIRMED_20_BAR_BREAKOUT" if proposal_decision == "NO_TRADE" else "GATE_REJECTED",
        "gate_reasons": ["NO_CONFIRMED_20_BAR_BREAKOUT"] if proposal_decision == "NO_TRADE" else ["GATE_REJECTED"],
        "gate_evidence": evidence,
        "strategy_family_route": route,
        "strategy_family_context_status": "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED",
        "strategy_run_provenance": {
            "code_release_id": "release-sha",
            "run_id": "run-123",
            "run_manifest_sha256": "c" * 64,
        },
        "evidence_source": "gateio_public_spot",
        "execution_enabled": False,
        "orders_placed": False,
        "outcome": None,
        "closed_at": None,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_projects_strategy_family_gate_attribution_and_provenance(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    event = read_decision_journal(path)["events"][0]
    assert event["decision_gate"] == "STRATEGY_POLICY"
    assert event["rejected_at"] == "STRATEGY_POLICY"
    assert event["reason_codes"] == ["NO_CONFIRMED_20_BAR_BREAKOUT"]
    assert event["strategy_family_id"] == "trend_breakout"
    assert event["strategy_family_version"] == "hes-btcusdt-mtf-confirmed-breakout-v2.0.0"
    assert event["strategy_family_activation_state"] == "CANDIDATE_LOCKED_NOT_ACTIVE"
    assert event["strategy_family_context_status"] == "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED"
    assert event["market_data_batch_sha256_by_timeframe"] == {"15m": "a" * 64, "1h": "b" * 64}
    assert event["code_release_id"] == "release-sha"
    assert event["run_id"] == "run-123"
    assert event["run_manifest_sha256"] == "c" * 64
    assert event["gate_summary"]["confirmation"]["failed_checks"] == ["direction_regime_alignment"]
    assert event["gate_summary"]["risk"]["failed_checks"] == ["confirmation_valid"]


def test_rejection_stage_uses_confirmation_then_risk_then_final_policy(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="UNCONFIRMED", risk_state="RISK_REJECTED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "CONFIRMATION"

    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="CONFIRMED_LONG", risk_state="RISK_REJECTED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "RISK"

    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="CONFIRMED_LONG", risk_state="RISK_APPROVED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "FINAL_POLICY"


def test_missing_gate_evidence_is_not_given_invented_attribution(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    record = {
        "event_id": "legacy-no-trade",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": "NO_TRADE",
        "evidence_source": "gateio_public_spot",
        "execution_enabled": False,
        "orders_placed": False,
        "outcome": None,
        "closed_at": None,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    event = read_decision_journal(path)["events"][0]
    assert event["decision_gate"] == "UNKNOWN"
    assert event["rejected_at"] == "UNKNOWN"



def test_missing_confirmation_does_not_become_final_policy_attribution(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="UNKNOWN", risk_state="RISK_APPROVED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "CONFIRMATION"


def test_projects_independent_family_candidate_confirmation_and_evidence(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    family_candidate = {
        "family_id": "range_mean_reversion",
        "family_version": "hes-range-mean-reversion-research-v1.0.0",
        "state": "CANDIDATE_LONG", "direction": "LONG",
        "evidence_sha256": "d" * 64, "execution_enabled": False, "orders_placed": False,
    }
    family_confirmation = {
        "family_id": "range_mean_reversion",
        "family_version": family_candidate["family_version"],
        "state": "RESEARCH_CONFIRMED_LONG", "passed_count": 8, "required_count": 8,
        "reason_codes": ["RANGE_RESEARCH_CONFIRMATION_PASSED_RISK_GATE_STILL_REQUIRED"],
        "checks": [
            {"name": "range_persistence", "state": "PASS"},
            {"name": "cost_adjusted_geometry", "state": "PASS"},
        ],
        "confirmation_authority": False, "risk_gate_required": True,
        "candidate_generation_authorized": False, "execution_enabled": False, "orders_placed": False,
    }
    family_evidence = {
        "status": "READY", "evidence_sha256": "d" * 64,
        "cost_model_status": "ASSUMPTION_BASED",
        "candidate": family_candidate,
    }
    record["strategy_family_candidate"] = family_candidate
    record["strategy_family_confirmation"] = family_confirmation
    record["strategy_family_evidence"] = family_evidence
    record["gate_evidence"]["strategy_family_candidate"] = family_candidate
    record["gate_evidence"]["strategy_family_confirmation"] = family_confirmation
    record["gate_evidence"]["strategy_family_evidence"] = family_evidence
    record["strategy_family_route"] = {
        "family_id": "range_mean_reversion",
        "family_version": family_candidate["family_version"],
        "activation_state": "RESEARCH_ONLY_NOT_ACTIVE",
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    event = read_decision_journal(path)["events"][0]
    assert event["strategy_family_confirmation_state"] == "RESEARCH_CONFIRMED_LONG"
    assert event["strategy_family_candidate_state"] == "CANDIDATE_LONG"
    assert event["strategy_family_candidate_direction"] == "LONG"
    assert event["strategy_family_evidence_status"] == "READY"
    assert event["strategy_family_evidence_sha256"] == "d" * 64
    assert event["gate_summary"]["strategy_family_confirmation"]["state"] == "RESEARCH_CONFIRMED_LONG"
    assert event["gate_summary"]["strategy_family_confirmation"]["failed_checks"] == []


def test_family_projection_rejects_cross_family_candidate_or_digest_mismatch(tmp_path):
    from forward.trade_journal_view_v1 import JournalProjectionError

    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["strategy_family_route"] = {"family_id": "range_mean_reversion"}
    record["strategy_family_candidate"] = {
        "family_id": "trend_breakout", "state": "CANDIDATE_LONG",
        "direction": "LONG", "evidence_sha256": "a" * 64,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(JournalProjectionError, match="strategy_family_identity_mismatch"):
        read_decision_journal(path)


def test_family_projection_rejects_mismatched_candidate_and_evidence_hashes(tmp_path):
    from forward.trade_journal_view_v1 import JournalProjectionError

    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["strategy_family_route"] = {"family_id": "range_mean_reversion"}
    record["strategy_family_candidate"] = {
        "family_id": "range_mean_reversion", "state": "CANDIDATE_LONG",
        "direction": "LONG", "evidence_sha256": "a" * 64,
    }
    record["strategy_family_evidence"] = {"family_id": "range_mean_reversion", "status": "READY", "evidence_sha256": "b" * 64}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(JournalProjectionError, match="strategy_family_evidence_digest_mismatch"):
        read_decision_journal(path)


def test_family_projection_rejects_candidate_not_matching_evidence_bundle(tmp_path):
    from forward.trade_journal_view_v1 import JournalProjectionError

    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["strategy_family_route"] = {"family_id": "range_mean_reversion"}
    record["strategy_family_candidate"] = {
        "family_id": "range_mean_reversion", "family_version": "v1",
        "state": "CANDIDATE_LONG", "direction": "LONG",
        "evidence_sha256": "a" * 64, "source": "gateio_public_spot",
        "symbol": "BTC_USDT", "timeframe": "15m",
    }
    record["strategy_family_evidence"] = {
        "family_id": "range_mean_reversion", "candidate": {
            "family_id": "range_mean_reversion", "family_version": "v1",
            "state": "CANDIDATE_SHORT", "direction": "SHORT",
            "evidence_sha256": "a" * 64, "source": "gateio_public_spot",
            "symbol": "BTC_USDT", "timeframe": "15m",
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(JournalProjectionError, match="strategy_family_evidence_candidate_mismatch"):
        read_decision_journal(path)


def _research_assessment_fixture():
    from forward.strategy_family_research_dispatch_v1 import FAMILIES
    families={}
    for family_id, profile in FAMILIES.items():
        features={name:False for name in profile["features"]}
        required=list(profile["features"])
        reasons=["REQUIRED_RESEARCH_FEATURE_FALSE:"+",".join(required)]
        payload={
            "candle_window_sha256":"b"*64,"family_id":family_id,
            "family_version":profile["version"],"status":"NOT_ELIGIBLE",
            "direction":None,"features":features,"required_features":required,
            "diagnostics":{},"reason_codes":reasons,
            "observed_at":"2026-11-10T12:00:00+00:00",
        }
        families[family_id]={
            "family_id":family_id,"family_version":profile["version"],
            "status":"NOT_ELIGIBLE","direction":None,"features":features,
            "required_features":required,"diagnostics":{},"reason_codes":reasons,
            "candle_window_sha256":"b"*64,"observed_at":"2026-11-10T12:00:00+00:00",
            "candidate_generation_authorized":False,"confirmation_approved":False,
            "risk_approved":False,"execution_enabled":False,"orders_placed":False,
            "evidence_sha256":sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest(),
        }
    result={
        "schema":"hes_strategy_family_research_assessment_v1","version":"hes-strategy-family-research-assessment-v1.1.0",
        "status":"ASSESSED","source":"gateio_public_spot","symbol":"BTC_USDT",
        "setup_timeframe":"15m","observed_at":"2026-11-10T12:00:00+00:00",
        "market_observed_at":"2026-11-10T12:00:04+00:00",
        "regime":"RANGE","candle_window_sha256":"b"*64,
        "cost_model_status":"UNAVAILABLE","cost_model_sha256":None,"families":families,
        "research_dispatch_status":"NO_RESEARCH_FAMILY_ELIGIBLE",
        "research_dispatch_version":"hes-strategy-family-research-dispatch-v1.0.0",
        "research_eligible_family_ids":[],"candidate_generation_authorized":False,
        "confirmation_approved":False,"risk_approved":False,
        "execution_enabled":False,"orders_placed":False,
    }
    result["assessment_sha256"]=sha256(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
    return result


def test_projects_four_family_research_assessment_from_decision_journal():
    from forward.trade_journal_view_v1 import _family_attribution
    assessment=_research_assessment_fixture()
    result=_family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})
    projected=result["research_assessment"]
    assert set(projected["families"])=={"trend_continuation","breakout_retest","range_reversion","volatility_expansion"}
    assert projected["research_eligible_family_ids"]==[]
    assert projected["execution_enabled"] is False


def test_journal_rejects_research_assessment_hash_and_authority_tampering():
    from forward.trade_journal_view_v1 import _family_attribution
    assessment=_research_assessment_fixture()
    assessment["families"]["trend_continuation"]["candle_window_sha256"]="c"*64
    with pytest.raises(JournalProjectionError,match="assessment_digest_mismatch"):
        _family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})
    assessment=_research_assessment_fixture()
    assessment["families"]["range_reversion"]["execution_enabled"]=True
    assessment["assessment_sha256"]=sha256(json.dumps(
        {k:v for k,v in assessment.items() if k!="assessment_sha256"},
        sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False
    ).encode()).hexdigest()
    with pytest.raises(JournalProjectionError,match="authority_boundary"):
        _family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})


def test_journal_records_blocked_family_assessment_without_fabricating_features():
    from forward.trade_journal_view_v1 import _family_attribution
    assessment={
        "schema":"hes_strategy_family_research_assessment_v1","version":"v1",
        "status":"BLOCKED","source":"gateio_public_spot","symbol":"BTC_USDT",
        "setup_timeframe":"15m","observed_at":None,"reason_codes":["INSUFFICIENT_CLOSED_15M_HISTORY"],
        "families":{},"research_eligible_family_ids":[],
        "candidate_generation_authorized":False,"confirmation_approved":False,
        "risk_approved":False,"execution_enabled":False,"orders_placed":False,
    }
    assessment["assessment_sha256"]=sha256(json.dumps(assessment,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
    result=_family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})
    assert result["research_assessment"]["status"]=="BLOCKED"


def test_journal_rejects_unknown_or_changed_research_family_version():
    from forward.trade_journal_view_v1 import _family_attribution
    assessment=_research_assessment_fixture()
    assessment["families"]["trend_continuation"]["family_version"]="unregistered-version"
    assessment["assessment_sha256"]=sha256(json.dumps(
        {k:v for k,v in assessment.items() if k!="assessment_sha256"},
        sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False
    ).encode()).hexdigest()
    with pytest.raises(JournalProjectionError,match="research_version_mismatch"):
        _family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})


def test_journal_detects_resealed_assessment_with_tampered_family_evidence_digest():
    from forward.trade_journal_view_v1 import _family_attribution
    assessment=_research_assessment_fixture()
    assessment["families"]["breakout_retest"]["diagnostics"]={"net_rr_estimate":2.5}
    assessment["assessment_sha256"]=sha256(json.dumps(
        {k:v for k,v in assessment.items() if k!="assessment_sha256"},
        sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False
    ).encode()).hexdigest()
    with pytest.raises(JournalProjectionError,match="research_digest_mismatch"):
        _family_attribution({"gate_evidence":{"strategy_family_research_assessment":assessment}})