"""Append-only, provenance-bound Trend and Range paper-result projections.

The canonical candidate/outcome ledgers remain the source of truth. This module
creates separate family-specific result journals without rewriting history or
inferring a family for legacy/unattributed records. It never authorizes signals
or execution.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .forward_journal_v1 import ForwardJournalV1
from .strategy_family_router_v1 import (
    CANONICAL_SOURCE,
    CANONICAL_SYMBOL,
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    SETUP_TIMEFRAME,
    TREND_BREAKOUT_V2,
)

SCHEMA = "hes_strategy_family_result_event_v1"
REPORT_SCHEMA = "hes_strategy_family_results_report_v1"
PROJECTION_VERSION = "hes-strategy-family-journal-v1.0.0"

FAMILY_PROFILES = {
    TREND_BREAKOUT_V2.family_id: TREND_BREAKOUT_V2,
    RANGE_MEAN_REVERSION_RESEARCH_V1.family_id: RANGE_MEAN_REVERSION_RESEARCH_V1,
}
FAMILY_FILES = {
    "trend_breakout": "strategy_family_trend_breakout_results_v1.jsonl",
    "range_mean_reversion": "strategy_family_range_mean_reversion_results_v1.jsonl",
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"blank_jsonl_line:{path.name}:{number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"jsonl_row_not_object:{path.name}:{number}")
            rows.append(value)
    return rows


def _sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("candidate_event_id") or candidate.get("event_id")
    return value.strip() if isinstance(value, str) else ""


def _family_identity(candidate: Mapping[str, Any]) -> dict[str, str] | None:
    evidence = candidate.get("gate_evidence")
    route = evidence.get("strategy_family_route") if isinstance(evidence, Mapping) else None
    if not isinstance(route, Mapping):
        return None

    family_id = candidate.get("strategy_family_id") or route.get("family_id")
    if family_id not in FAMILY_PROFILES:
        return None
    profile = FAMILY_PROFILES[family_id]
    family_version = candidate.get("strategy_family_version") or route.get("family_version")
    activation_state = (
        candidate.get("strategy_family_activation_state")
        or route.get("activation_state")
    )

    if candidate.get("source") != CANONICAL_SOURCE or candidate.get("symbol") != CANONICAL_SYMBOL:
        raise ValueError("FAMILY_JOURNAL_CANONICAL_SOURCE_OR_SYMBOL_MISMATCH")
    if (
        route.get("symbol") != CANONICAL_SYMBOL
        or route.get("timeframe") != SETUP_TIMEFRAME
        or route.get("regime") not in profile.regimes
    ):
        raise ValueError("FAMILY_JOURNAL_ROUTE_SCOPE_MISMATCH")
    if family_version != profile.version or activation_state != profile.activation_state:
        raise ValueError("FAMILY_JOURNAL_PROFILE_VERSION_OR_ACTIVATION_MISMATCH")
    if (
        route.get("candidate_generation_authorized") is not False
        or route.get("execution_enabled") is not False
        or route.get("orders_placed") is not False
    ):
        raise ValueError("FAMILY_JOURNAL_ROUTE_AUTHORITY_BOUNDARY_VIOLATION")
    if (
        candidate.get("execution_enabled") is not False
        or candidate.get("orders_placed") is not False
    ):
        raise ValueError("FAMILY_JOURNAL_CANDIDATE_NOT_PAPER_ONLY")
    if candidate.get("strategy_family_id") not in (None, family_id):
        raise ValueError("FAMILY_JOURNAL_CANDIDATE_FAMILY_ID_MISMATCH")
    if candidate.get("strategy_family_version") not in (None, profile.version):
        raise ValueError("FAMILY_JOURNAL_CANDIDATE_FAMILY_VERSION_MISMATCH")

    return {
        "family_id": family_id,
        "family_version": profile.version,
        "activation_state": profile.activation_state,
        "regime": str(route["regime"]),
        "symbol": CANONICAL_SYMBOL,
        "timeframe": SETUP_TIMEFRAME,
    }


def _candidate_event(candidate: Mapping[str, Any], identity: Mapping[str, str]) -> dict[str, Any]:
    source_id = _candidate_id(candidate)
    if not source_id:
        raise ValueError("FAMILY_JOURNAL_CANDIDATE_EVENT_ID_MISSING")
    observed_at = candidate.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at:
        raise ValueError("FAMILY_JOURNAL_CANDIDATE_TIMESTAMP_MISSING")
    family_id = identity["family_id"]
    return {
        "schema": SCHEMA,
        "projection_version": PROJECTION_VERSION,
        "event_id": f"hes-family-{family_id}-candidate-{source_id}",
        "source_event_id": source_id,
        "source_file": "strategy_policy_v2_eval_candidates.jsonl",
        "source_record_sha256": _sha256(candidate),
        "event_type": "PAPER_CANDIDATE",
        **dict(identity),
        "observed_at": observed_at,
        "candidate_time": candidate.get("candidate_time"),
        "candidate_event_id": source_id,
        "direction": candidate.get("direction"),
        "entry": candidate.get("entry"),
        "stop_loss": candidate.get("stop_loss"),
        "take_profit": candidate.get("take_profit"),
        "rr": candidate.get("rr"),
        "final_gate_decision": candidate.get("final_gate_decision"),
        "final_gate_reasons": candidate.get("final_gate_reasons", []),
        "preapproval_paper_eligible": candidate.get("preapproval_paper_eligible"),
        "preapproval_paper_status": candidate.get("preapproval_paper_status"),
        "code_release_id": candidate.get("code_release_id"),
        "run_id": candidate.get("run_id"),
        "source_hashes": candidate.get("source_hashes"),
        "execution_enabled": False,
        "orders_placed": False,
    }


def _outcome_event(
    outcome: Mapping[str, Any],
    candidate: Mapping[str, Any],
    identity: Mapping[str, str],
) -> dict[str, Any]:
    source_id = outcome.get("event_id")
    candidate_id = _candidate_id(candidate)
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("FAMILY_JOURNAL_OUTCOME_EVENT_ID_MISSING")
    if outcome.get("candidate_event_id") != candidate_id:
        raise ValueError("FAMILY_JOURNAL_OUTCOME_CANDIDATE_LINK_MISMATCH")
    if (
        outcome.get("execution_enabled") is not False
        or outcome.get("orders_placed") is not False
    ):
        raise ValueError("FAMILY_JOURNAL_OUTCOME_NOT_PAPER_ONLY")
    if outcome.get("strategy_family_id") not in (None, identity["family_id"]):
        raise ValueError("FAMILY_JOURNAL_OUTCOME_FAMILY_ID_MISMATCH")
    if outcome.get("strategy_family_version") not in (None, identity["family_version"]):
        raise ValueError("FAMILY_JOURNAL_OUTCOME_FAMILY_VERSION_MISMATCH")
    resolved_at = outcome.get("resolved_at") or outcome.get("observed_at")
    if not isinstance(resolved_at, str) or not resolved_at:
        raise ValueError("FAMILY_JOURNAL_OUTCOME_TIMESTAMP_MISSING")
    return {
        "schema": SCHEMA,
        "projection_version": PROJECTION_VERSION,
        "event_id": f"hes-family-{identity['family_id']}-outcome-{source_id}",
        "source_event_id": source_id,
        "source_file": "strategy_policy_v2_eval_outcomes.jsonl",
        "source_record_sha256": _sha256(outcome),
        "candidate_source_sha256": _sha256(candidate),
        "event_type": "PAPER_OUTCOME",
        **dict(identity),
        "observed_at": resolved_at,
        "resolved_at": resolved_at,
        "candidate_time": outcome.get("candidate_time", candidate.get("candidate_time")),
        "candidate_event_id": candidate_id,
        "direction": outcome.get("direction", candidate.get("direction")),
        "entry": outcome.get("entry", candidate.get("entry")),
        "stop_loss": outcome.get("stop_loss", candidate.get("stop_loss")),
        "take_profit": outcome.get("take_profit", candidate.get("take_profit")),
        "outcome": outcome.get("outcome"),
        "outcome_reason": outcome.get("reason"),
        "exit_price": outcome.get("exit_price"),
        "exit_close": outcome.get("exit_close"),
        "final_gate_decision": outcome.get(
            "final_gate_decision", candidate.get("final_gate_decision")
        ),
        "performance_eligible": outcome.get("performance_eligible"),
        "preapproval_paper_eligible": outcome.get(
            "preapproval_paper_eligible", candidate.get("preapproval_paper_eligible")
        ),
        "code_release_id": outcome.get("code_release_id", candidate.get("code_release_id")),
        "run_id": outcome.get("run_id", candidate.get("run_id")),
        "source_hashes": outcome.get("source_hashes", candidate.get("source_hashes")),
        "execution_enabled": False,
        "orders_placed": False,
    }


def _journal_summary(path: Path, family_id: str, profile: Any) -> dict[str, Any]:
    rows = _load_jsonl(path)
    seen: set[str] = set()
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in seen:
            raise ValueError(f"FAMILY_JOURNAL_EVENT_ID_INVALID:{family_id}")
        seen.add(event_id)
        if row.get("family_id") != family_id:
            raise ValueError(f"FAMILY_JOURNAL_CROSS_FAMILY_CONTAMINATION:{family_id}")
        if (
            row.get("execution_enabled") is not False
            or row.get("orders_placed") is not False
        ):
            raise ValueError(f"FAMILY_JOURNAL_UNSAFE_RECORD:{family_id}")

    candidates = [row for row in rows if row.get("event_type") == "PAPER_CANDIDATE"]
    outcomes = [row for row in rows if row.get("event_type") == "PAPER_OUTCOME"]
    raw = Counter(str(row.get("outcome", "UNKNOWN")) for row in outcomes)
    eligible = [
        row for row in outcomes
        if row.get("performance_eligible") is True
        and row.get("outcome") in ("wins", "losses", "flats")
    ]
    wins = sum(row.get("outcome") == "wins" for row in eligible)
    resolved = len(eligible)
    return {
        "family_id": family_id,
        "family_version": profile.version,
        "activation_state": profile.activation_state,
        "status": profile.activation_state,
        "candidate_count": len(candidates),
        "outcome_count": len(outcomes),
        "raw_outcome_counts": dict(raw),
        "performance_eligible_resolved": resolved,
        "performance_eligible_wins": wins,
        "performance_eligible_win_rate_pct": (
            round(100.0 * wins / resolved, 2) if resolved else None
        ),
        "preapproval_paper_eligible_outcomes": sum(
            row.get("preapproval_paper_eligible") is True for row in outcomes
        ),
        "journal_event_count": len(rows),
        "journal_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        "journal_file": path.name,
        "execution_enabled": False,
        "orders_placed": False,
    }


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sync_strategy_family_result_journals(
    *,
    candidates_path: str | Path,
    outcomes_path: str | Path,
    output_dir: str | Path,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Idempotently project explicitly attributed candidates/outcomes into two journals."""
    candidates_file = Path(candidates_path)
    outcomes_file = Path(outcomes_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report_file = Path(report_path) if report_path is not None else destination / "strategy_family_results_report_v1.json"

    candidates = _load_jsonl(candidates_file)
    outcomes = _load_jsonl(outcomes_file)
    candidate_index: dict[str, dict[str, Any]] = {}
    identities: dict[str, dict[str, str] | None] = {}
    unattributed_candidates = 0

    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        if not candidate_id:
            unattributed_candidates += 1
            continue
        if candidate_id in candidate_index:
            raise ValueError("FAMILY_JOURNAL_DUPLICATE_CANDIDATE_ID")
        candidate_index[candidate_id] = candidate
        identity = _family_identity(candidate)
        identities[candidate_id] = identity
        if identity is None:
            unattributed_candidates += 1

    unattributed_outcomes = 0
    unmatched_outcomes = 0
    projected: dict[str, list[dict[str, Any]]] = {
        family_id: [] for family_id in FAMILY_PROFILES
    }

    for candidate_id, candidate in candidate_index.items():
        identity = identities[candidate_id]
        if identity is None:
            continue
        projected[identity["family_id"]].append(_candidate_event(candidate, identity))

    for outcome in outcomes:
        candidate_id = outcome.get("candidate_event_id")
        candidate = candidate_index.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is None:
            unmatched_outcomes += 1
            continue
        identity = identities.get(candidate_id)
        if identity is None:
            unattributed_outcomes += 1
            continue
        projected[identity["family_id"]].append(_outcome_event(outcome, candidate, identity))

    appended: dict[str, int] = {}
    for family_id, profile in FAMILY_PROFILES.items():
        path = destination / FAMILY_FILES[family_id]
        path.touch(exist_ok=True)
        existing_rows = _load_jsonl(path)
        existing_ids = {row.get("event_id") for row in existing_rows}
        writer = ForwardJournalV1(path)
        appended[family_id] = 0
        for event in projected[family_id]:
            if event["event_id"] in existing_ids:
                continue
            if writer.append_event(event):
                appended[family_id] += 1
                existing_ids.add(event["event_id"])
        # Validate the entire family journal after append/replay.
        _journal_summary(path, family_id, profile)

    families = {
        family_id: _journal_summary(destination / FAMILY_FILES[family_id], family_id, profile)
        for family_id, profile in FAMILY_PROFILES.items()
    }
    report = {
        "schema": REPORT_SCHEMA,
        "projection_version": PROJECTION_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_candidates_file": candidates_file.name,
        "canonical_outcomes_file": outcomes_file.name,
        "attribution_policy": "EXPLICIT_VERSIONED_FAMILY_ROUTE_AND_EXACT_CANDIDATE_EVENT_ID_ONLY",
        "unattributed_candidate_count": unattributed_candidates,
        "unattributed_outcome_count": unattributed_outcomes,
        "unmatched_outcome_count": unmatched_outcomes,
        "new_records_appended": appended,
        "families": families,
        "execution_enabled": False,
        "orders_placed": False,
    }
    _write_report(report_file, report)
    return report
