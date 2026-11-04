"""Read-only Mother orchestration adapter for the canonical Strategy V2 evidence.

This adapter consumes already-produced Strategy V2 report/journal outputs. It does
not fetch candles, rerun indicators, recompute structure/strategy/risk, write journals,
or authorize execution. A missing or mismatched evidence link fails closed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

from core.orchestration.mother_v1 import MotherOrchestratorV1, precomputed_specialists_v1
from core.orchestration.witness_v1 import MotherAuditWitnessV1
from web.strategy_v2_dashboard_view import StrategyV2DashboardError, read_strategy_v2_dashboard

_EXPECTED_SOURCE = "gateio_public_spot"
_EXPECTED_SYMBOL = "BTC_USDT"
_ALLOWED_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}
_ADAPTER_VERSION = "hes-mother-v2-evidence-adapter-v1"


class MotherV2DashboardError(ValueError):
    """Canonical Strategy V2 evidence cannot be safely orchestrated."""


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise MotherV2DashboardError("invalid_mother_evidence_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MotherV2DashboardError("invalid_mother_evidence_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MotherV2DashboardError("naive_mother_evidence_timestamp")
    return parsed.astimezone(timezone.utc)


def _reason_codes(value: Any, code: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise MotherV2DashboardError(code)
    if len(value) != len(set(value)):
        raise MotherV2DashboardError(code + "_duplicated")
    return value


def _check_refs(value: Any, fallback: str) -> list[str]:
    if not isinstance(value, list):
        return [fallback]
    refs = []
    for row in value:
        if isinstance(row, Mapping):
            ref = row.get("evidence_ref")
            if isinstance(ref, str) and ref:
                refs.append(ref)
    return list(dict.fromkeys(refs)) or [fallback]


def read_mother_v2_dashboard(
    *,
    strategy_view: Mapping[str, Any] | None = None,
    report_path: str | None = None,
    journal_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run Mother over the exact V2 report + matching immutable journal decision."""
    try:
        view = strategy_view or read_strategy_v2_dashboard(
            report_path=report_path, journal_path=journal_path, now=now
        )
    except StrategyV2DashboardError as exc:
        raise MotherV2DashboardError("strategy_v2_evidence_blocked:" + str(exc)) from exc

    if not isinstance(view, Mapping) or view.get("status") != "VERIFIED":
        raise MotherV2DashboardError("strategy_v2_view_not_verified")
    if view.get("source") != _EXPECTED_SOURCE or view.get("symbol") != _EXPECTED_SYMBOL:
        raise MotherV2DashboardError("strategy_v2_market_identity_mismatch")
    if view.get("execution_enabled") is not False or view.get("orders_placed") is not False:
        raise MotherV2DashboardError("strategy_v2_execution_boundary_violation")

    candle_time = view.get("closed_15m_candle_time")
    if isinstance(candle_time, bool) or not isinstance(candle_time, int) or candle_time <= 0:
        raise MotherV2DashboardError("strategy_v2_closed_candle_identity_missing")
    expected_event_id = f"hes-v2-{_EXPECTED_SYMBOL}-15m-{candle_time}"

    journal = view.get("journal")
    if not isinstance(journal, Mapping) or journal.get("status") != "VERIFIED":
        raise MotherV2DashboardError("canonical_journal_not_verified")
    events = journal.get("events")
    if not isinstance(events, list):
        raise MotherV2DashboardError("canonical_journal_events_invalid")
    event = next(
        (row for row in events if isinstance(row, Mapping) and row.get("event_id") == expected_event_id),
        None,
    )
    if event is None:
        raise MotherV2DashboardError("matching_v2_decision_event_missing")

    if (
        event.get("source") != _EXPECTED_SOURCE
        or event.get("symbol") != _EXPECTED_SYMBOL
        or event.get("timeframe") != "15m"
        or event.get("execution") != "OFF"
        or event.get("decision") not in _ALLOWED_DECISIONS
        or event.get("signal_state") not in _ALLOWED_DECISIONS
    ):
        raise MotherV2DashboardError("v2_journal_event_identity_or_safety_mismatch")

    gate = view.get("latest_gate_evidence")
    if not isinstance(gate, Mapping):
        raise MotherV2DashboardError("v2_gate_evidence_missing")
    if (
        gate.get("source") != _EXPECTED_SOURCE
        or gate.get("symbol") != _EXPECTED_SYMBOL
        or gate.get("timeframe") != "15m"
        or gate.get("final_decision") != event.get("decision")
    ):
        raise MotherV2DashboardError("v2_gate_journal_decision_mismatch")
    market_data_provenance = view.get("market_data_provenance")
    if (
        not isinstance(market_data_provenance, Mapping)
        or gate.get("market_data_provenance") != market_data_provenance
        or market_data_provenance.get("schema") != "hes_market_data_batch_provenance_v1"
        or market_data_provenance.get("source") != _EXPECTED_SOURCE
        or market_data_provenance.get("symbol") != _EXPECTED_SYMBOL
    ):
        raise MotherV2DashboardError("v2_market_data_provenance_unverified")
    timeframe_provenance = market_data_provenance.get("timeframes")
    if not isinstance(timeframe_provenance, Mapping) or set(timeframe_provenance) != {"15m", "1h", "4h"}:
        raise MotherV2DashboardError("v2_market_data_provenance_timeframes_invalid")
    batch_refs = []
    for timeframe in ("15m", "1h", "4h"):
        item = timeframe_provenance.get(timeframe)
        digest = item.get("input_batch_sha256") if isinstance(item, Mapping) else None
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise MotherV2DashboardError("v2_market_data_batch_digest_invalid:" + timeframe)
        batch_refs.append(f"market_batch:{timeframe}:sha256:{digest}")

    structure = gate.get("structure")
    confirmation = gate.get("confirmation")
    risk = gate.get("risk")
    if not all(isinstance(x, Mapping) for x in (structure, confirmation, risk)):
        raise MotherV2DashboardError("v2_specialist_evidence_incomplete")
    if (
        structure.get("regime") != event.get("market_regime")
        or confirmation.get("state") != event.get("confirmation_state")
        or risk.get("state") != event.get("risk_state")
    ):
        raise MotherV2DashboardError("v2_specialist_journal_mismatch")

    market_observed = _timestamp(view.get("market_evidence_observed_at"))
    event_observed = _timestamp(event.get("observed_at"))
    report_updated = _timestamp(view.get("updated_at"))
    if abs((event_observed - market_observed).total_seconds()) > 900:
        raise MotherV2DashboardError("v2_journal_event_outside_candle_observation_window")
    if (event_observed - report_updated).total_seconds() > 5:
        raise MotherV2DashboardError("v2_journal_event_newer_than_report")

    report_sha = view.get("report_sha256")
    event_sha = event.get("event_sha256")
    if (
        not isinstance(report_sha, str) or len(report_sha) != 64
        or not isinstance(event_sha, str) or len(event_sha) != 64
    ):
        raise MotherV2DashboardError("v2_evidence_digest_missing")

    confirmation_reasons = _reason_codes(
        confirmation.get("reason_codes", []), "v2_confirmation_reason_codes_invalid"
    )
    risk_reasons = _reason_codes(risk.get("reason_codes", []), "v2_risk_reason_codes_invalid")
    event_reasons = _reason_codes(event.get("reason_codes", []), "v2_signal_reason_codes_invalid")

    pipeline_version = gate.get("pipeline_version")
    final_gate_version = view.get("final_gate_version")
    policy_version = view.get("agent_version")
    if not all(isinstance(x, str) and x for x in (pipeline_version, final_gate_version, policy_version)):
        raise MotherV2DashboardError("v2_agent_version_missing")

    confirmation_state = (
        "CONFIRMED"
        if confirmation.get("state") in {"CONFIRMED_LONG", "CONFIRMED_SHORT"}
        else "UNCONFIRMED"
    )
    risk_state = "APPROVED" if risk.get("state") == "RISK_APPROVED" else str(risk.get("state") or "UNKNOWN")
    structure_state = (
        "PASS"
        if structure.get("status") == "OBSERVED" and structure.get("regime") not in (None, "", "UNKNOWN")
        else "UNKNOWN"
    )
    signal_state = "PASS" if event.get("signal_state") in _ALLOWED_DECISIONS else "UNKNOWN"
    decision = str(event.get("decision"))

    specialist_reports = {
        "data_quality": {
            "agent_version": _ADAPTER_VERSION,
            "state": "PASS",
            "reason_codes": [],
            "evidence_refs": [f"report_sha256:{report_sha}", f"journal_event_sha256:{event_sha}", *batch_refs],
            "payload": {"source": _EXPECTED_SOURCE, "symbol": _EXPECTED_SYMBOL, "event_id": expected_event_id,
                        "input_batch_sha256_by_timeframe": {tf: timeframe_provenance[tf]["input_batch_sha256"] for tf in ("15m", "1h", "4h")}},
        },
        "market_structure": {
            "agent_version": pipeline_version,
            "state": structure_state,
            "reason_codes": [] if structure_state == "PASS" else ["STRUCTURE_EVIDENCE_NOT_OBSERVED"],
            "evidence_refs": [f"structure_sha256:{_canonical_hash(dict(structure))}", f"journal_event_sha256:{event_sha}"],
            "payload": {"regime": structure.get("regime"), "observed_at": structure.get("observed_at")},
        },
        "signal": {
            "agent_version": policy_version,
            "state": signal_state,
            "reason_codes": event_reasons,
            "evidence_refs": [f"journal_event_sha256:{event_sha}", f"signal_state:{event.get('signal_state')}", *batch_refs],
            "payload": {"decision": event.get("signal_state"), "direction": event.get("direction")},
        },
        "confirmation": {
            "agent_version": pipeline_version,
            "state": confirmation_state,
            "reason_codes": confirmation_reasons,
            "evidence_refs": _check_refs(
                confirmation.get("checks"), f"confirmation_sha256:{_canonical_hash(dict(confirmation))}"
            ),
            "payload": {"upstream_state": confirmation.get("state")},
        },
        "risk": {
            "agent_version": pipeline_version,
            "state": risk_state,
            "reason_codes": risk_reasons,
            "evidence_refs": _check_refs(
                risk.get("checks"), f"risk_sha256:{_canonical_hash(dict(risk))}"
            ),
            "payload": {"upstream_state": risk.get("state")},
        },
        "decision": {
            "agent_version": final_gate_version,
            "state": "DECIDED",
            "reason_codes": event_reasons,
            "evidence_refs": [f"journal_event_sha256:{event_sha}", f"decision:{decision}"],
            "payload": {"decision": decision},
        },
        "evaluation": {
            "agent_version": _ADAPTER_VERSION,
            "state": "OBSERVED",
            "reason_codes": [],
            "evidence_refs": [f"report_sha256:{report_sha}", f"journal_event_sha256:{event_sha}"],
            "payload": {"outcomes_inferred": False},
        },
    }
    evidence_sha = _canonical_hash(specialist_reports)
    context = {
        "scope": {"venue": "gateio", "product": "spot", "symbol": _EXPECTED_SYMBOL, "timeframe": "15m"},
        "observed_at": report_updated.isoformat(),
        "snapshot_sha256": report_sha,
        "market_data_provenance": market_data_provenance,
        "evidence_sha256": evidence_sha,
        "request_id": expected_event_id,
        "specialist_reports": specialist_reports,
    }
    result = MotherOrchestratorV1(precomputed_specialists_v1()).run(context)
    envelope = result.as_dict()
    witness = MotherAuditWitnessV1().verify(envelope)
    if not witness.verified:
        raise MotherV2DashboardError("mother_witness_rejected:" + "|".join(witness.reason_codes))

    return {
        "schema": "hes.mother_v2_dashboard_view.v1",
        "status": result.status,
        "decision": result.decision,
        "reason_codes": list(result.reason_codes),
        "trace_id": result.trace_id,
        "audit_sha256": result.audit_sha256,
        "market_data_provenance": market_data_provenance,
        "stages": envelope["stages"],
        "witness": witness.as_dict(),
        "source": _EXPECTED_SOURCE,
        "symbol": _EXPECTED_SYMBOL,
        "timeframe": "15m",
        "matched_event_id": expected_event_id,
        "report_sha256": report_sha,
        "journal_event_sha256": event_sha,
        "execution_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
        "outcomes_inferred": False,
    }
