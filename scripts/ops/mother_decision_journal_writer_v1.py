#!/usr/bin/env python3
"""Persist witnessed Mother decisions to the existing append-only HES journal."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path("/opt/hes-trade-agent")
CODE_ROOT = Path(__file__).resolve().parents[2]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from forward.forward_journal_v1 import ForwardJournalV1  # noqa: E402

SCHEMA = "hes_mother_decision_journal_event_v1"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
TIMEFRAME = "15m"
VALID_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _utc_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("MOTHER_OBSERVED_AT_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("MOTHER_OBSERVED_AT_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("MOTHER_OBSERVED_AT_NAIVE")
    parsed = parsed.astimezone(timezone.utc)
    if (parsed - datetime.now(timezone.utc)).total_seconds() > 5:
        raise ValueError("MOTHER_OBSERVED_AT_FUTURE")
    return parsed.isoformat()


def _stage_map(stages: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(stages, list):
        raise ValueError("MOTHER_STAGES_INVALID")
    result: dict[str, dict[str, Any]] = {}
    for row in stages:
        if not isinstance(row, dict):
            raise ValueError("MOTHER_STAGE_INVALID")
        name = row.get("agent")
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("MOTHER_STAGE_ID_INVALID")
        result[name] = row
    return result


def _candidate_and_proposal(mother: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal = mother.get("strategy_proposal")
    proposal = proposal if isinstance(proposal, dict) else {}
    lane = mother.get("strategy_family_paper_lane")
    lane = lane if isinstance(lane, dict) else {}
    candidate = lane.get("selected_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    return proposal, candidate


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _stable_stage_evidence(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stable = []
    for row in stages:
        refs = row.get("evidence_refs", [])
        if not isinstance(refs, list):
            refs = []
        # context_sha256 includes wall-clock age/observation time; raw news
        # snapshot and brief hashes are retained separately and are stable.
        stable_prefixes = (
            "market_batch:", "strategy_proposal_sha256:",
            "strategy_family_paper_lane_sha256:",
            "news_snapshot_sha256:", "news_brief_sha256:",
        )
        refs = sorted(
            ref for ref in refs
            if isinstance(ref, str) and ref.startswith(stable_prefixes)
        )
        stable.append({
            "agent": row.get("agent"),
            "agent_version": row.get("agent_version"),
            "state": row.get("state"),
            "reason_codes": sorted(row.get("reason_codes", []))
            if isinstance(row.get("reason_codes"), list) else [],
            "evidence_refs": refs,
        })
    return stable


def build_mother_journal_record(mother: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a witnessed runtime envelope and map it to a journal event."""
    if not isinstance(mother, Mapping):
        raise ValueError("MOTHER_ENVELOPE_INVALID")
    if mother.get("schema") != "hes.mother_runtime_dashboard.v1":
        raise ValueError("MOTHER_SCHEMA_INVALID")
    if mother.get("runtime_mode") != "LIVE_DATA_RUNTIME_SPECIALISTS":
        raise ValueError("MOTHER_RUNTIME_NOT_LIVE")
    if mother.get("source") != SOURCE or mother.get("symbol") != SYMBOL or mother.get("timeframe") != TIMEFRAME:
        raise ValueError("MOTHER_MARKET_SCOPE_INVALID")
    if mother.get("execution_authorized") is not False:
        raise ValueError("MOTHER_EXECUTION_AUTHORITY_MUST_REMAIN_OFF")
    for key in ("execution_enabled", "orders_placed", "outcomes_inferred"):
        if mother.get(key) is not False:
            raise ValueError("MOTHER_SAFETY_BOUNDARY_VIOLATION:" + key)
    if mother.get("external_llm_used") is not False:
        raise ValueError("MOTHER_EXTERNAL_LLM_BOUNDARY_VIOLATION")
    if mother.get("journal_write") is not False:
        raise ValueError("MOTHER_READ_API_MUST_REMAIN_READ_ONLY")

    witness = mother.get("witness")
    if not isinstance(witness, dict) or witness.get("verified") is not True:
        raise ValueError("MOTHER_WITNESS_NOT_VERIFIED")
    if witness.get("execution_authorized") is not False:
        raise ValueError("MOTHER_WITNESS_AUTHORITY_INVALID")

    decision = mother.get("decision")
    if decision not in VALID_DECISIONS:
        raise ValueError("MOTHER_DECISION_INVALID")
    observed_at = _utc_timestamp(mother.get("observed_at"))
    snapshot_sha = mother.get("snapshot_sha256")
    audit_sha = mother.get("audit_sha256")
    trace_id = mother.get("trace_id")
    if not _is_sha(snapshot_sha) or not _is_sha(audit_sha) or not _is_sha(trace_id):
        raise ValueError("MOTHER_PROVENANCE_HASH_INVALID")

    stages = mother.get("stages")
    stage_by_name = _stage_map(stages)
    consensus = mother.get("consensus")
    if not isinstance(consensus, dict):
        raise ValueError("MOTHER_CONSENSUS_MISSING")
    news = mother.get("news_context")
    news = news if isinstance(news, dict) else {}
    proposal, candidate = _candidate_and_proposal(mother)

    candidate_direction = candidate.get("direction")
    proposal_direction = proposal.get("direction")
    if candidate_direction not in ("LONG", "SHORT"):
        candidate_direction = None
    if proposal_direction not in ("LONG", "SHORT"):
        proposal_direction = None
    direction = candidate_direction or proposal_direction
    if decision in ("LONG", "SHORT"):
        direction = decision
    if direction not in ("LONG", "SHORT"):
        direction = "NONE"

    entry = _number(candidate.get("entry") or candidate.get("reference_price") or proposal.get("entry"))
    stop_loss = _number(candidate.get("stop_loss") or candidate.get("stop") or proposal.get("stop_loss"))
    take_profit = _number(candidate.get("take_profit") or candidate.get("target") or proposal.get("take_profit"))
    rr = _number(candidate.get("rr") or proposal.get("rr"))
    if not (direction in ("LONG", "SHORT") and entry and stop_loss and take_profit):
        entry = stop_loss = take_profit = rr = None

    stage_order = ("data_quality", "market_structure", "signal", "confirmation", "risk", "decision", "evaluation")
    ordered_stages = [stage_by_name[name] for name in stage_order if name in stage_by_name]
    failed_stage = next((
        row.get("agent") for row in ordered_stages
        if row.get("state") not in {
            "PASS", "CONFIRMED", "APPROVED", "DECIDED", "OBSERVED",
        }
    ), None)
    decision_gate = (failed_stage or "MOTHER_CONSENSUS").upper()
    confirmation_state = str(stage_by_name.get("confirmation", {}).get("state", "UNKNOWN"))
    risk_state = str(stage_by_name.get("risk", {}).get("state", "UNKNOWN"))
    signal_state = str(stage_by_name.get("signal", {}).get("state", "UNKNOWN"))

    reasons: list[str] = []
    for values in (
        mother.get("reason_codes"),
        consensus.get("reason_codes"),
        proposal.get("reason_codes"),
        (mother.get("strategy_family_paper_lane") or {}).get("reason_codes")
        if isinstance(mother.get("strategy_family_paper_lane"), dict) else [],
    ):
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value and value not in reasons:
                    reasons.append(value)
    for row in ordered_stages:
        for value in row.get("reason_codes", []) if isinstance(row.get("reason_codes"), list) else []:
            if isinstance(value, str) and value and value not in reasons:
                reasons.append(value)

    provenance = mother.get("market_data_provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    stable_timeframes = {}
    timeframes = provenance.get("timeframes")
    if isinstance(timeframes, dict):
        for timeframe, detail in sorted(timeframes.items()):
            if not isinstance(detail, dict):
                continue
            stable_timeframes[timeframe] = {
                key: detail.get(key)
                for key in (
                    "source", "symbol", "timeframe", "input_batch_sha256",
                    "batch_candles", "closed_candles", "latest_close_time",
                    "max_age_seconds",
                )
                if key in detail
            }
    stable_market_provenance = {
        "source": provenance.get("source"),
        "symbol": provenance.get("symbol"),
        "timeframes": stable_timeframes,
    }
    stable_identity = {
        "schema": SCHEMA,
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "snapshot_sha256": snapshot_sha,
        "market_data_provenance": stable_market_provenance,
        "news_snapshot_sha256": news.get("snapshot_sha256"),
        "news_brief_sha256": news.get("brief_sha256"),
        "stable_stage_evidence": _stable_stage_evidence(ordered_stages),
        "consensus": {
            "decision": consensus.get("decision"),
            "direction": consensus.get("direction"),
            "conflict_class": consensus.get("conflict_class"),
            "reason_codes": sorted(consensus.get("reason_codes", []))
            if isinstance(consensus.get("reason_codes"), list) else [],
        },
        "proposal": {
            "decision": proposal.get("decision"),
            "direction": proposal.get("direction"),
            "policy_version": proposal.get("policy_version"),
            "quality_score": proposal.get("quality_score"),
            "reason_codes": sorted(proposal.get("reason_codes", []))
            if isinstance(proposal.get("reason_codes"), list) else [],
        },
        "candidate": candidate,
        "decision": decision,
        "status": mother.get("status"),
    }
    event_id = "hes-mother-" + _sha(stable_identity)

    family_route = candidate.get("strategy_family_route")
    family_route = family_route if isinstance(family_route, dict) else {}
    family_id = (candidate.get("parent_family_id") or family_route.get("family_id")
                 or candidate.get("strategy_family_id") or candidate.get("family_id"))
    family_version = (family_route.get("family_version") or candidate.get("strategy_family_version")
                      or candidate.get("family_version"))
    family_activation_state = (family_route.get("activation_state")
                               or candidate.get("strategy_family_activation_state")
                               or candidate.get("live_activation_state"))
    policy_version = proposal.get("policy_version") or family_version or "hes-mother-orchestrator-v1"

    record = {
        "schema": SCHEMA,
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "source": SOURCE,
        "product": "spot",
        "evidence_source": SOURCE,
        "service_name": "mother_runtime_decision_journal_writer",
        "decision": decision,
        "direction": direction,
        "proposal_decision": proposal.get("decision", "UNKNOWN"),
        "proposal_direction": direction,
        "proposal_entry": entry,
        "proposal_stop_loss": stop_loss,
        "proposal_take_profit": take_profit,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": rr,
        "candidate_event_id": candidate.get("event_id"),
        "candidate_entry_semantics": candidate.get("entry_semantics"),
        "quality_score": candidate.get("quality_score", proposal.get("quality_score")),
        "market_regime": mother.get("market_regime", "UNKNOWN"),
        "status": mother.get("status", "UNKNOWN"),
        "policy_version": policy_version,
        "strategy_family_id": family_id,
        "strategy_family_version": family_version,
        "strategy_family_activation_state": family_activation_state,
        "witness_verified": True,
        "decision_gate": decision_gate,
        "rejected_at": decision_gate,
        "signal_state": signal_state,
        "confirmation_state": confirmation_state,
        "risk_state": risk_state,
        "no_trade_reason": "|".join(reasons) if decision == "NO_TRADE" else None,
        "reason_codes": reasons,
        "gate_reasons": reasons,
        "gate_evidence": {
            "mother_schema": mother.get("schema"),
            "mother_status": mother.get("status"),
            "trace_id": trace_id,
            "audit_sha256": audit_sha,
            "snapshot_sha256": snapshot_sha,
            "consensus": consensus,
            "stages": ordered_stages,
            "strategy_proposal": proposal,
            "strategy_family_paper_lane": mother.get("strategy_family_paper_lane"),
            "news_context": news,
            "market_data_provenance": provenance,
            "execution_enabled": False,
            "orders_placed": False,
        },
        "source_hashes": {
            "mother_snapshot_sha256": snapshot_sha,
            "mother_audit_sha256": audit_sha,
            "mother_trace_id": trace_id,
            "news_snapshot_sha256": news.get("snapshot_sha256"),
            "news_brief_sha256": news.get("brief_sha256"),
        },
        "execution_enabled": False,
        "orders_placed": False,
        "outcomes_inferred": False,
        "policy_mutation_enabled": False,
        "outcome": None,
        "closed_at": None,
    }
    return record


def run_once(
    *,
    data_root: str | Path = ROOT,
    journal_path: str | Path | None = None,
    mother_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if mother_payload is None:
        from web.mother_runtime_dashboard_view import read_mother_runtime_dashboard
        mother_payload = read_mother_runtime_dashboard(data_root=data_root)
    record = build_mother_journal_record(mother_payload)
    target = Path(journal_path or os.environ.get(
        "HES_TRADE_JOURNAL_PATH",
        str(Path(data_root) / "data/forward/trade_journal_v2.jsonl"),
    ))
    appended = ForwardJournalV1(target).append_event(record)
    return {
        "schema": "hes_mother_decision_journal_writer_result_v1",
        "status": "RECORDED" if appended else "ALREADY_RECORDED",
        "event_id": record["event_id"],
        "decision": record["decision"],
        "observed_at": record["observed_at"],
        "journal_path": str(target),
        "execution_enabled": False,
        "orders_placed": False,
        "policy_mutation_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one witnessed Mother observation")
    parser.add_argument("--journal", type=Path, default=None)
    args = parser.parse_args()
    if not args.once:
        parser.error("use --once")
    state_dir = Path(os.environ.get("STATE_DIRECTORY", "/var/tmp/hes-mother-journal-writer"))
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_once(journal_path=args.journal)
        result["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = state_dir / "latest.json.tmp"
        target = state_dir / "latest.json"
        temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        result = {
            "schema": "hes_mother_decision_journal_writer_result_v1",
            "status": "BLOCKED",
            "reason_code": type(exc).__name__ + ":" + str(exc)[:240],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "execution_enabled": False,
            "orders_placed": False,
            "policy_mutation_enabled": False,
        }
        temporary = state_dir / "latest.json.tmp"
        target = state_dir / "latest.json"
        temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        print(json.dumps(result, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
