"""Read-only projection of the canonical mixed HES trade journal.

Paper candidates/outcomes and Signal Agent decisions share one append-only file.
Only LONG/SHORT/NO_TRADE decision records are projected here; realized outcomes
are never inferred or written back into a decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Any

from .strategy_family_research_dispatch_v1 import FAMILIES as RESEARCH_FAMILY_CONTRACTS

MAX_LINE_BYTES = 1024 * 1024
MAX_ROWS = 100
_ALLOWED_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}


def _reason_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return [item for item in value if item]
    raise JournalProjectionError("invalid_reason_codes")


def _market_batch_hashes(record: dict[str, Any]) -> dict[str, str]:
    provenance = record.get("market_data_provenance")
    if provenance is None:
        evidence = record.get("gate_evidence")
        provenance = evidence.get("market_data_provenance") if isinstance(evidence, dict) else None
    if provenance is None:
        return {}
    if not isinstance(provenance, dict):
        raise JournalProjectionError("invalid_market_data_provenance")
    timeframes = provenance.get("timeframes", {})
    if not isinstance(timeframes, dict):
        raise JournalProjectionError("invalid_market_data_timeframes")
    result: dict[str, str] = {}
    for timeframe, batch in timeframes.items():
        if not isinstance(timeframe, str) or not isinstance(batch, dict):
            raise JournalProjectionError("invalid_market_data_timeframe_record")
        digest = batch.get("input_batch_sha256")
        if digest is None:
            continue
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise JournalProjectionError("invalid_market_data_batch_sha256")
        result[timeframe] = digest
    return result


def _family_attribution(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("gate_evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise JournalProjectionError("invalid_gate_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}

    def selected(key: str):
        top_level = record.get(key)
        nested = evidence.get(key)
        if top_level is not None and nested is not None and top_level != nested:
            raise JournalProjectionError("strategy_family_journal_field_mismatch:" + key)
        value = top_level if top_level is not None else nested
        if value is not None and not isinstance(value, dict):
            raise JournalProjectionError("invalid_strategy_family_payload:" + key)
        return value

    candidate = selected("strategy_family_candidate") or {}
    confirmation = selected("strategy_family_confirmation") or {}
    family_evidence = selected("strategy_family_evidence") or {}
    nested_candidate = family_evidence.get("candidate")
    if nested_candidate is not None and not isinstance(nested_candidate, dict):
        raise JournalProjectionError("invalid_strategy_family_payload:strategy_family_evidence.candidate")
    if not candidate and isinstance(nested_candidate, dict):
        candidate = nested_candidate
    elif candidate and isinstance(nested_candidate, dict):
        for field in ("family_id", "family_version", "state", "direction", "evidence_sha256", "source", "symbol", "timeframe"):
            if candidate.get(field) != nested_candidate.get(field):
                raise JournalProjectionError("strategy_family_evidence_candidate_mismatch")
    route = record.get("strategy_family_route") or evidence.get("strategy_family_route") or {}
    if not isinstance(route, dict):
        raise JournalProjectionError("invalid_strategy_family_route")
    route_family_id = route.get("family_id")
    for payload in (candidate, confirmation, family_evidence):
        payload_family_id = payload.get("family_id")
        if payload_family_id is not None and payload_family_id != route_family_id:
            raise JournalProjectionError("strategy_family_identity_mismatch")

    candidate_state = candidate.get("state")
    candidate_direction = candidate.get("direction")
    if candidate_state is not None and candidate_state not in ("CANDIDATE_LONG", "CANDIDATE_SHORT"):
        raise JournalProjectionError("invalid_strategy_family_candidate_state")
    expected_direction = {"CANDIDATE_LONG": "LONG", "CANDIDATE_SHORT": "SHORT"}.get(candidate_state)
    if candidate_direction is not None and expected_direction is not None and candidate_direction != expected_direction:
        raise JournalProjectionError("strategy_family_candidate_direction_mismatch")

    confirmation_state = confirmation.get("state")
    if confirmation_state is not None and not isinstance(confirmation_state, str):
        raise JournalProjectionError("invalid_strategy_family_confirmation_state")
    evidence_status = family_evidence.get("status")
    if evidence_status is not None and evidence_status not in ("READY", "NO_CANDIDATE", "BLOCKED"):
        raise JournalProjectionError("invalid_strategy_family_evidence_status")

    research = evidence.get("strategy_family_research_assessment")
    research_projection = None
    if research is not None:
        expected_ids = {"trend_continuation", "breakout_retest", "range_reversion", "volatility_expansion"}
        if not isinstance(research, dict) or research.get("schema") != "hes_strategy_family_research_assessment_v1":
            raise JournalProjectionError("invalid_strategy_family_research_assessment")
        assessment_digest = research.get("assessment_sha256")
        assessment_payload = {key: value for key, value in research.items() if key != "assessment_sha256"}
        expected_assessment_digest = sha256(json.dumps(
            assessment_payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if not isinstance(assessment_digest, str) or assessment_digest != expected_assessment_digest:
            raise JournalProjectionError("strategy_family_research_assessment_digest_mismatch")
        if research.get("status") == "BLOCKED":
            if not isinstance(research.get("reason_codes"), list) or not research["reason_codes"]:
                raise JournalProjectionError("strategy_family_research_block_reason_missing")
            if research.get("families") != {} or research.get("research_eligible_family_ids") != []:
                raise JournalProjectionError("strategy_family_research_blocked_payload_not_empty")
            if any(research.get(flag) is not False for flag in (
                "candidate_generation_authorized", "confirmation_approved", "risk_approved",
                "execution_enabled", "orders_placed"
            )):
                raise JournalProjectionError("strategy_family_research_authority_boundary_violation")
            research_projection = {
                "schema": research["schema"], "version": research.get("version"),
                "assessment_sha256": assessment_digest, "status": "BLOCKED", "reason_codes": list(research["reason_codes"]),
                "source": research.get("source"), "symbol": research.get("symbol"),
                "setup_timeframe": research.get("setup_timeframe"),
                "execution_enabled": False, "orders_placed": False,
            }
        else:
            if research.get("status") != "ASSESSED":
                raise JournalProjectionError("strategy_family_research_status_invalid")
            if (research.get("source"), research.get("symbol"), research.get("setup_timeframe")) != (
                "gateio_public_spot", "BTC_USDT", "15m"
            ):
                raise JournalProjectionError("strategy_family_research_scope_mismatch")
            candle_hash = research.get("candle_window_sha256")
            if not isinstance(candle_hash, str) or len(candle_hash) != 64 or any(ch not in "0123456789abcdef" for ch in candle_hash):
                raise JournalProjectionError("strategy_family_research_candle_hash_invalid")
            if research.get("regime") not in ("UPTREND", "DOWNTREND", "RANGE", "UNKNOWN"):
                raise JournalProjectionError("strategy_family_research_regime_invalid")
            try:
                observed_stamp = datetime.fromisoformat(str(research.get("observed_at", "")).replace("Z", "+00:00"))
                market_observed_stamp = datetime.fromisoformat(str(research.get("market_observed_at", "")).replace("Z", "+00:00"))
                if (observed_stamp.tzinfo is None or observed_stamp.utcoffset() is None
                        or market_observed_stamp.tzinfo is None or market_observed_stamp.utcoffset() is None):
                    raise ValueError("naive")
                observation_lag=(market_observed_stamp-observed_stamp).total_seconds()
                if observation_lag < 0 or observation_lag > 900:
                    raise ValueError("observation_lag")
            except (TypeError, ValueError):
                raise JournalProjectionError("strategy_family_research_observed_at_invalid")
            top_cost_status = research.get("cost_model_status")
            top_cost_hash = research.get("cost_model_sha256")
            if top_cost_status not in ("ASSUMPTION_BASED", "UNAVAILABLE", "VERIFIED"):
                raise JournalProjectionError("strategy_family_research_top_cost_status_invalid")
            if top_cost_hash is not None and (not isinstance(top_cost_hash, str) or len(top_cost_hash) != 64 or any(ch not in "0123456789abcdef" for ch in top_cost_hash)):
                raise JournalProjectionError("strategy_family_research_top_cost_hash_invalid")
            if (top_cost_status == "ASSUMPTION_BASED" and top_cost_hash is None) or (top_cost_status == "UNAVAILABLE" and top_cost_hash is not None):
                raise JournalProjectionError("strategy_family_research_top_cost_binding_invalid")
            families = research.get("families")
            if not isinstance(families, dict) or set(families) != expected_ids:
                raise JournalProjectionError("strategy_family_research_family_set_invalid")
            eligible_ids = []
            family_projection = {}
            for family_id, item in families.items():
                if not isinstance(item, dict) or item.get("family_id") != family_id:
                    raise JournalProjectionError("strategy_family_research_identity_mismatch")
                if item.get("family_version") != RESEARCH_FAMILY_CONTRACTS[family_id]["version"]:
                    raise JournalProjectionError("strategy_family_research_version_mismatch")
                features = item.get("features")
                required = item.get("required_features")
                if not isinstance(features, dict) or not isinstance(required, list) or not required or len(required) != len(set(required)) or not set(required).issubset(features):
                    raise JournalProjectionError("strategy_family_research_features_invalid")
                if any(type(value) is not bool for value in features.values()):
                    raise JournalProjectionError("strategy_family_research_feature_value_invalid")
                diagnostics = item.get("diagnostics", {})
                if not isinstance(diagnostics, dict):
                    raise JournalProjectionError("strategy_family_research_diagnostics_invalid")
                net_rr = diagnostics.get("net_rr_estimate")
                if net_rr is not None and (isinstance(net_rr, bool) or not isinstance(net_rr, (int, float)) or not math.isfinite(float(net_rr))):
                    raise JournalProjectionError("strategy_family_research_net_rr_invalid")
                cost_status = diagnostics.get("cost_model_status")
                if cost_status is not None and cost_status not in ("ASSUMPTION_BASED", "UNAVAILABLE", "VERIFIED"):
                    raise JournalProjectionError("strategy_family_research_cost_status_invalid")
                cost_hash = diagnostics.get("cost_model_sha256")
                if cost_hash is not None and (not isinstance(cost_hash, str) or len(cost_hash) != 64 or any(ch not in "0123456789abcdef" for ch in cost_hash)):
                    raise JournalProjectionError("strategy_family_research_cost_hash_invalid")
                if cost_status == "ASSUMPTION_BASED" and cost_hash != top_cost_hash:
                    raise JournalProjectionError("strategy_family_research_cost_model_mismatch")
                digest = item.get("evidence_sha256")
                if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                    raise JournalProjectionError("strategy_family_research_digest_invalid")
                if item.get("candle_window_sha256") != candle_hash or item.get("observed_at") != research.get("observed_at"):
                    raise JournalProjectionError("strategy_family_research_provenance_mismatch")
                digest_payload = {
                    "candle_window_sha256": candle_hash, "family_id": family_id,
                    "family_version": item.get("family_version"),
                    "status": item.get("status"), "direction": item.get("direction"),
                    "features": features, "required_features": required,
                    "diagnostics": diagnostics,
                    "reason_codes": item.get("reason_codes", []),
                    "observed_at": research.get("observed_at"),
                }
                expected_digest = sha256(json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False,
                ).encode("utf-8")).hexdigest()
                if digest != expected_digest:
                    raise JournalProjectionError("strategy_family_research_digest_mismatch")
                if any(item.get(flag) is not False for flag in (
                    "candidate_generation_authorized", "confirmation_approved", "risk_approved",
                    "execution_enabled", "orders_placed"
                )):
                    raise JournalProjectionError("strategy_family_research_authority_boundary_violation")
                should_eligible = all(features[name] for name in required)
                if item.get("direction") not in (None, "LONG", "SHORT"):
                    raise JournalProjectionError("strategy_family_research_direction_invalid")
                if not isinstance(item.get("reason_codes"), list) or any(not isinstance(code, str) for code in item["reason_codes"]):
                    raise JournalProjectionError("strategy_family_research_reason_codes_invalid")
                if item.get("status") not in ("RESEARCH_ELIGIBLE", "NOT_ELIGIBLE") or (item.get("status") == "RESEARCH_ELIGIBLE") != should_eligible:
                    raise JournalProjectionError("strategy_family_research_status_mismatch")
                if should_eligible:
                    eligible_ids.append(family_id)
                family_projection[family_id] = {
                    "family_version": item["family_version"],
                    "status": item["status"], "direction": item.get("direction"),
                    "features": dict(features), "required_features": list(required),
                    "reason_codes": item.get("reason_codes", []),
                    "diagnostics": dict(diagnostics), "evidence_sha256": digest,
                }
            if set(research.get("research_eligible_family_ids", [])) != set(eligible_ids):
                raise JournalProjectionError("strategy_family_research_eligibility_mismatch")
            expected_dispatch_status = "RESEARCH_DISPATCHED" if eligible_ids else "NO_RESEARCH_FAMILY_ELIGIBLE"
            if (research.get("research_dispatch_status") != expected_dispatch_status
                    or research.get("research_dispatch_version") != "hes-strategy-family-research-dispatch-v1.0.0"):
                raise JournalProjectionError("strategy_family_research_dispatch_binding_invalid")
            if any(research.get(flag) is not False for flag in (
                "candidate_generation_authorized", "confirmation_approved", "risk_approved",
                "execution_enabled", "orders_placed"
            )):
                raise JournalProjectionError("strategy_family_research_top_level_authority_violation")
            research_projection = {
                "schema": research["schema"], "version": research.get("version"),
                "assessment_sha256": assessment_digest, "status": research.get("status"),
                "observed_at": research.get("observed_at"),
                "market_observed_at": research.get("market_observed_at"),
                "regime": research.get("regime"),
                "candle_window_sha256": candle_hash,
                "cost_model_status": top_cost_status, "cost_model_sha256": top_cost_hash,
                "research_eligible_family_ids": sorted(eligible_ids),
                "families": family_projection,
                "execution_enabled": False, "orders_placed": False,
            }

    candidate_digest = candidate.get("evidence_sha256")
    evidence_digest = family_evidence.get("evidence_sha256")
    for digest in (candidate_digest, evidence_digest):
        if digest is not None and (
            not isinstance(digest, str) or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest.lower())
        ):
            raise JournalProjectionError("invalid_strategy_family_evidence_sha256")
    if candidate_digest is not None and evidence_digest is not None and candidate_digest != evidence_digest:
        raise JournalProjectionError("strategy_family_evidence_digest_mismatch")

    return {
        "confirmation_state": confirmation_state,
        "candidate_state": candidate_state,
        "candidate_direction": candidate_direction,
        "evidence_status": evidence_status,
        "evidence_sha256": evidence_digest or candidate_digest,
        "research_assessment": research_projection,
    }


def _rejection_stage(record: dict[str, Any]) -> str:
    """Return only a gate stage supported by the immutable decision evidence."""
    explicit = record.get("rejected_at")
    if explicit is not None and not isinstance(explicit, str):
        raise JournalProjectionError("invalid_rejected_at")
    if isinstance(explicit, str) and explicit.strip() and explicit not in {"—", "-", "UNKNOWN"}:
        return explicit
    if record.get("decision") != "NO_TRADE":
        return "—"

    if record.get("proposal_decision") == "NO_TRADE":
        return "STRATEGY_POLICY"

    evidence = record.get("gate_evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise JournalProjectionError("invalid_gate_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    confirmation = evidence.get("confirmation")
    confirmation = confirmation if isinstance(confirmation, dict) else {}
    risk = evidence.get("risk")
    risk = risk if isinstance(risk, dict) else {}
    confirmation_state = confirmation.get("state") or record.get("confirmation_state")
    risk_state = risk.get("state") or record.get("risk_state")

    proposal = record.get("proposal_decision")
    confirmed = confirmation_state in {"CONFIRMED_LONG", "CONFIRMED_SHORT"}
    if proposal in {"LONG", "SHORT"}:
        if confirmation_state is None:
            return "UNKNOWN"
        if not confirmed:
            return "CONFIRMATION"
        if risk_state is None:
            return "UNKNOWN"
        if risk_state != "RISK_APPROVED":
            return "RISK"
        return "FINAL_POLICY"
    if confirmation_state and not confirmed:
        return "CONFIRMATION"
    if confirmed and risk_state and risk_state != "RISK_APPROVED":
        return "RISK"
    return "UNKNOWN"


def _gate_summary(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("gate_evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise JournalProjectionError("invalid_gate_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    result: dict[str, Any] = {
        "strategy_state": record.get("proposal_decision") or record.get("signal_state") or "UNKNOWN",
        "strategy_reason_codes": _reason_list(record.get("proposal_reasons")),
    }
    for name in ("confirmation", "strategy_family_confirmation", "risk"):
        stage = evidence.get(name)
        stage = stage if isinstance(stage, dict) else {}
        checks = stage.get("checks")
        checks = checks if isinstance(checks, list) else []
        result[name] = {
            "state": stage.get("state") or record.get(name + "_state") or "UNKNOWN",
            "reason_codes": _reason_list(stage.get("reason_codes")),
            "failed_checks": [
                item.get("name") for item in checks
                if isinstance(item, dict) and item.get("state") == "FAIL" and isinstance(item.get("name"), str)
            ],
            "unknown_checks": [
                item.get("name") for item in checks
                if isinstance(item, dict) and item.get("state") == "UNKNOWN" and isinstance(item.get("name"), str)
            ],
        }
    return result


class JournalProjectionError(ValueError):
    """The canonical journal cannot safely be projected to the UI."""


def read_decision_journal(
    path: str | Path,
    *,
    limit: int = 50,
    now: datetime | None = None,
    expected_source: str | None = None,
    expected_symbol: str | None = None,
    expected_policy_version: str | None = None,
    require_execution_off: bool = False,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise JournalProjectionError("invalid_limit")
    file_path = Path(path)
    try:
        if file_path.is_symlink() or not file_path.is_file():
            raise JournalProjectionError("journal_not_a_regular_file")
        size = file_path.stat().st_size
        if size == 0:
            return {"schema": "hes.trade_journal_view.v1", "status": "EMPTY", "count": 0, "decision_count": 0, "events": []}
        with file_path.open("rb") as handle:
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                raise JournalProjectionError("partial_trailing_record")
    except JournalProjectionError:
        raise
    except OSError as exc:
        raise JournalProjectionError("journal_unavailable") from exc

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JournalProjectionError("verifier_clock_not_timezone_aware")
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_records = 0
    decision_total = 0
    try:
        with file_path.open("rb") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                if len(raw_line) > MAX_LINE_BYTES:
                    raise JournalProjectionError(f"record_size_limit_exceeded:{line_no}")
                if not raw_line.endswith(b"\n"):
                    raise JournalProjectionError("partial_trailing_record")
                try:
                    record = json.loads(raw_line.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise JournalProjectionError(f"invalid_json:{line_no}") from exc
                if not isinstance(record, dict):
                    raise JournalProjectionError(f"invalid_record_shape:{line_no}")
                total_records += 1
                event_id = record.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    raise JournalProjectionError(f"missing_event_id:{line_no}")
                if event_id in seen:
                    raise JournalProjectionError(f"duplicate_event:{line_no}")
                seen.add(event_id)
                if record.get("decision") not in _ALLOWED_DECISIONS:
                    continue
                decision_total += 1
                source = record.get("source") or record.get("evidence_source")
                if expected_source is not None and source != expected_source:
                    raise JournalProjectionError(f"unexpected_source:{line_no}")
                if expected_symbol is not None and record.get("symbol") != expected_symbol:
                    raise JournalProjectionError(f"unexpected_symbol:{line_no}")
                if expected_policy_version is not None and record.get("policy_version") != expected_policy_version:
                    raise JournalProjectionError(f"unexpected_policy_version:{line_no}")
                if require_execution_off and (
                    record.get("execution_enabled") is not False or record.get("orders_placed") is not False
                ):
                    raise JournalProjectionError(f"execution_boundary_violation:{line_no}")
                if record.get("outcome") is not None or record.get("closed_at") is not None:
                    raise JournalProjectionError(f"outcome_leakage_in_decision_journal:{line_no}")
                observed_at = record.get("observed_at")
                if not isinstance(observed_at, str):
                    raise JournalProjectionError(f"invalid_timestamp:{line_no}")
                try:
                    parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise JournalProjectionError(f"invalid_timestamp:{line_no}") from exc
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise JournalProjectionError(f"naive_timestamp:{line_no}")
                if (parsed - current).total_seconds() > 5:
                    raise JournalProjectionError(f"future_timestamp:{line_no}")
                rejected_at = _rejection_stage(record)
                if record.get("decision_gate") is not None and not isinstance(record.get("decision_gate"), str):
                    raise JournalProjectionError(f"invalid_decision_gate:{line_no}")
                decision_gate = record.get("decision_gate")
                if not decision_gate or decision_gate in {"UNKNOWN", "—", "-"}:
                    decision_gate = rejected_at
                reasons = _reason_list(record.get("reason_codes"))
                if not reasons and rejected_at == "STRATEGY_POLICY":
                    reasons = _reason_list(record.get("proposal_reasons"))
                if not reasons:
                    reasons = _reason_list(record.get("gate_reasons"))
                if not reasons:
                    reasons = _reason_list(record.get("final_gate_reasons"))
                if not reasons and record.get("no_trade_reason"):
                    reasons = str(record["no_trade_reason"]).split("|")
                if not reasons:
                    gate_evidence = record.get("gate_evidence")
                    if isinstance(gate_evidence, dict):
                        stage = gate_evidence.get(rejected_at.lower()) if rejected_at in {"CONFIRMATION", "RISK"} else None
                        if isinstance(stage, dict):
                            reasons = _reason_list(stage.get("reason_codes"))
                if any(not isinstance(reason, str) for reason in reasons):
                    raise JournalProjectionError(f"invalid_reason_codes:{line_no}")
                evidence_source = record.get("evidence_source")
                if not isinstance(evidence_source, (str, list, tuple)):
                    raise JournalProjectionError(f"missing_evidence_source:{line_no}")
                family = _family_attribution(record)
                events.append({
                    "event_id": event_id,
                    "observed_at": parsed.astimezone(timezone.utc).isoformat(),
                    "symbol": record.get("symbol", "UNKNOWN"),
                    "timeframe": record.get("timeframe", "UNKNOWN"),
                    "decision": record["decision"],
                    "direction": record.get("direction", "NONE"),
                    "status": record.get("status", "RECORDED"),
                    "market_regime": record.get("market_regime", "UNKNOWN"),
                    "decision_gate": decision_gate,
                    "rejected_at": rejected_at,
                    "signal_state": record.get("signal_state", "UNKNOWN"),
                    "confirmation_state": record.get("confirmation_state", "UNKNOWN"),
                    "risk_state": record.get("risk_state", "UNKNOWN"),
                    "reason_codes": reasons,
                    "source": source,
                    "product": record.get("product", "UNKNOWN"),
                    "policy_version": record.get("policy_version", "UNKNOWN"),
                    "response_sha256": record.get("response_sha256"),
                    "htf_response_sha256": record.get("htf_response_sha256"),
                    "strategy_family_id": record.get("strategy_family_id") or (
                        record.get("strategy_family_route", {}).get("family_id")
                        if isinstance(record.get("strategy_family_route"), dict) else None
                    ),
                    "strategy_family_version": record.get("strategy_family_version") or (
                        record.get("strategy_family_route", {}).get("family_version")
                        if isinstance(record.get("strategy_family_route"), dict) else None
                    ),
                    "strategy_family_activation_state": record.get("strategy_family_activation_state") or (
                        record.get("strategy_family_route", {}).get("activation_state")
                        if isinstance(record.get("strategy_family_route"), dict) else None
                    ),
                    "strategy_family_context_status": record.get("strategy_family_context_status"),
                    "strategy_family_confirmation_state": family["confirmation_state"],
                    "strategy_family_candidate_state": family["candidate_state"],
                    "strategy_family_candidate_direction": family["candidate_direction"],
                    "strategy_family_evidence_status": family["evidence_status"],
                    "strategy_family_evidence_sha256": family["evidence_sha256"],
                    "strategy_family_research_assessment": family["research_assessment"],
                    "gate_summary": _gate_summary(record),
                    "market_data_batch_sha256_by_timeframe": _market_batch_hashes(record),
                    "code_release_id": record.get("code_release_id") or (
                        record.get("strategy_run_provenance", {}).get("code_release_id")
                        if isinstance(record.get("strategy_run_provenance"), dict) else None
                    ),
                    "run_id": record.get("run_id") or (
                        record.get("strategy_run_provenance", {}).get("run_id")
                        if isinstance(record.get("strategy_run_provenance"), dict) else None
                    ),
                    "run_manifest_sha256": record.get("run_manifest_sha256") or (
                        record.get("strategy_run_provenance", {}).get("run_manifest_sha256")
                        if isinstance(record.get("strategy_run_provenance"), dict) else None
                    ),
                    "event_sha256": sha256(raw_line.rstrip(b"\r\n")).hexdigest(),
                    "execution": "OFF" if record.get("execution_enabled") is False and record.get("orders_placed") is False else "UNKNOWN",
                    "realized_outcome": "NOT_LINKED",
                })
                if len(events) > MAX_ROWS * 2:
                    events.sort(key=lambda item: (item["observed_at"], item["event_id"]), reverse=True)
                    del events[MAX_ROWS:]
    except JournalProjectionError:
        raise
    except OSError as exc:
        raise JournalProjectionError("journal_unavailable") from exc

    events.sort(key=lambda item: (item["observed_at"], item["event_id"]), reverse=True)
    return {
        "schema": "hes.trade_journal_view.v1",
        "status": "VERIFIED",
        "count": total_records,
        "decision_count": decision_total,
        "events": events[:limit],
        "truncated": total_records > limit,
        "execution_enabled": False,
        "outcomes_inferred": False,
    }


def configured_decision_journal(*, journal_path: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    configured = os.environ.get("HES_TRADE_JOURNAL_PATH", "").strip()
    path = Path(configured) if configured else Path(journal_path) if journal_path is not None else None
    if path is None or not path.is_file():
        return {
            "schema": "hes.trade_journal_view.v1",
            "status": "NOT_CONFIGURED",
            "count": 0,
            "decision_count": 0,
            "events": [],
            "execution_enabled": False,
            "outcomes_inferred": False,
        }
    return read_decision_journal(path, limit=limit)