"""Read-only projection of the canonical mixed HES trade journal.

Paper candidates/outcomes and Signal Agent decisions share one append-only file.
Only LONG/SHORT/NO_TRADE decision records are projected here; realized outcomes
are never inferred or written back into a decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

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

    if confirmation_state and confirmation_state not in {"CONFIRMED_LONG", "CONFIRMED_SHORT"}:
        return "CONFIRMATION"
    if risk_state and risk_state != "RISK_APPROVED":
        return "RISK"
    if record.get("proposal_decision") in {"LONG", "SHORT"} and risk_state == "RISK_APPROVED":
        return "FINAL_POLICY"
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
    for name in ("confirmation", "risk"):
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
                events.append({
                    "event_id": event_id,
                    "observed_at": parsed.astimezone(timezone.utc).isoformat(),
                    "symbol": record.get("symbol", "UNKNOWN"),
                    "timeframe": record.get("timeframe", "UNKNOWN"),
                    "decision": record["decision"],
                    "direction": record.get("direction", "NONE"),
                    "status": record.get("status", "RECORDED"),
                    "market_regime": record.get("market_regime", "UNKNOWN"),
                    "decision_gate": record.get("decision_gate") or rejected_at,
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
