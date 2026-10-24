"""Bridge the existing Signal Agent to immutable forward-learning evidence.

Decision observations and realized outcomes are separate append-only artifacts.
This module never infers outcomes, tunes a strategy, or authorizes execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .forward_observation_writer_v1 import (
    ForwardObservationWriterV1,
    canonical_json,
    observation_digest,
)
from .learning_loop_v1 import LearningReport, build_learning_report
from .runtime_guard_v1 import RuntimeContext

OUTCOME_VALUES = frozenset({"OPEN", "WIN", "LOSS", "BREAKEVEN", "CANCELLED"})
CLOSED_OUTCOMES = frozenset({"WIN", "LOSS", "BREAKEVEN"})


@dataclass(frozen=True)
class JournalWriteResult:
    status: str
    event_id: str
    digest: str


def _digest_without_field(record: Mapping, field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def record_signal_decision(
    journal_path: str | Path,
    *,
    decision: str,
    observed_at: str,
    symbol: str,
    timeframe: str,
    source: str,
    product: str,
    response_sha256: str,
    htf_response_sha256: str,
    strategy_evidence_sha256: str | None,
    policy_version: str,
    status: str,
    market_regime: str,
    rejected_at: str,
    reason_codes: Iterable[str],
) -> JournalWriteResult:
    """Persist a deterministic, idempotent decision event; never persist outcomes."""
    if decision not in {"LONG", "SHORT", "NO_TRADE"}:
        raise ValueError("invalid_decision")
    for name, value in (
        ("observed_at", observed_at), ("symbol", symbol), ("timeframe", timeframe),
        ("source", source), ("product", product), ("policy_version", policy_version),
        ("status", status), ("market_regime", market_regime),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_" + name)
    if not isinstance(rejected_at, str):
        raise ValueError("invalid_rejected_at")
    for name, value in (
        ("response_sha256", response_sha256),
        ("htf_response_sha256", htf_response_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid_" + name)
    if strategy_evidence_sha256 is not None and (
        not isinstance(strategy_evidence_sha256, str) or len(strategy_evidence_sha256) != 64
        or any(c not in "0123456789abcdef" for c in strategy_evidence_sha256)
    ):
        raise ValueError("invalid_strategy_evidence_sha256")
    reasons = list(reason_codes)
    if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
        raise ValueError("invalid_reason_codes")

    # Event identity pins immutable inputs + policy version, not the output.
    # If the same inputs later produce a different decision, it becomes a conflict.
    identity = {
        "observed_at": observed_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "product": product,
        "response_sha256": response_sha256,
        "htf_response_sha256": htf_response_sha256,
        "strategy_evidence_sha256": strategy_evidence_sha256,
        "policy_version": policy_version,
    }
    identity_sha = sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    run_id = "signal-" + identity_sha
    event_id = run_id + ":decision"
    payload = {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": status,
        "source": source,
        "product": product,
        "artifact_kind": "SIGNAL_DECISION",
        "decision": decision,
        "market_regime": market_regime,
        "decision_gate": rejected_at or "SIGNAL_AGENT",
        "rejected_at": rejected_at,
        "reason_codes": reasons,
        "response_sha256": response_sha256,
        "htf_response_sha256": htf_response_sha256,
        "strategy_evidence_sha256": strategy_evidence_sha256,
        "policy_version": policy_version,
        "source_period": "forward",
        "execution": "OFF",
    }
    context = RuntimeContext(source=source, observed_at=observed_at, forward_run_id=run_id)
    try:
        digest = ForwardObservationWriterV1(journal_path).append(payload, context=context)
        return JournalWriteResult("RECORDED", event_id, digest)
    except ValueError as exc:
        if "duplicate observation event_id" not in str(exc):
            raise
        # The writer owns locking and duplicate detection. Verify that the existing
        # immutable event is byte-for-byte equivalent in canonical digest terms.
        path = Path(journal_path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("event_id") == event_id:
                expected_payload = {**payload, "artifact_type": "FORWARD_OBSERVATION", "artifact_version": "1.0"}
                expected = observation_digest(expected_payload)
                if existing.get("digest") == expected:
                    return JournalWriteResult("ALREADY_RECORDED", event_id, expected)
                raise ValueError("conflicting_duplicate_decision_event")
        raise


def build_report_from_artifacts(
    decision_records: Iterable[Mapping],
    outcome_records: Iterable[Mapping],
    *,
    min_group_size: int = 5,
) -> LearningReport:
    """Join forward-only decisions to separately recorded, digest-verified outcomes."""
    decisions = [dict(item) for item in decision_records]
    outcomes = [dict(item) for item in outcome_records]
    decision_by_id: dict[str, dict] = {}
    for row in decisions:
        if row.get("artifact_type") != "FORWARD_OBSERVATION":
            raise ValueError("decision_artifact_type_invalid")
        if row.get("artifact_kind") != "SIGNAL_DECISION":
            raise ValueError("non_decision_observation_in_learning_population")
        if row.get("source_period") != "forward" or row.get("execution") != "OFF":
            raise ValueError("decision_population_not_forward_only")
        if row.get("outcome") is not None or row.get("closed_at") is not None:
            raise ValueError("outcome_must_be_separate_artifact")
        if not isinstance(row.get("digest"), str) or _digest_without_field(row, "digest") != row["digest"]:
            raise ValueError("decision_digest_mismatch")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("decision_event_id_missing")
        if event_id in decision_by_id:
            raise ValueError("duplicate_decision_event_id")
        decision_by_id[event_id] = row

    outcome_by_decision: dict[str, dict] = {}
    outcome_event_ids: set[str] = set()
    for row in outcomes:
        if row.get("artifact_type") != "FORWARD_OUTCOME":
            raise ValueError("outcome_artifact_type_invalid")
        if row.get("source_period") != "forward":
            raise ValueError("outcome_population_not_forward_only")
        if row.get("execution") != "OFF":
            raise ValueError("outcome_execution_scope_invalid")
        outcome_event_id = row.get("outcome_event_id")
        if not isinstance(outcome_event_id, str) or not outcome_event_id.strip() or outcome_event_id in outcome_event_ids:
            raise ValueError("duplicate_or_missing_outcome_event_id")
        outcome_event_ids.add(outcome_event_id)
        if not isinstance(row.get("digest"), str) or _digest_without_field(row, "digest") != row["digest"]:
            raise ValueError("outcome_digest_mismatch")
        evidence_sha = row.get("evidence_sha256")
        if not isinstance(evidence_sha, str) or len(evidence_sha) != 64 or any(
            char not in "0123456789abcdef" for char in evidence_sha
        ):
            raise ValueError("invalid_outcome_evidence_sha256")
        if not isinstance(row.get("evidence_ref"), str) or not row["evidence_ref"].strip():
            raise ValueError("outcome_evidence_ref_required")
        decision_event_id = row.get("decision_event_id")
        if decision_event_id not in decision_by_id:
            raise ValueError("outcome_without_known_forward_decision")
        if row.get("decision_digest") != decision_by_id[decision_event_id].get("digest"):
            raise ValueError("outcome_decision_digest_mismatch")
        if decision_event_id in outcome_by_decision:
            raise ValueError("multiple_outcomes_for_decision")
        outcome = row.get("outcome")
        if not isinstance(outcome, str) or outcome not in OUTCOME_VALUES:
            raise ValueError("invalid_outcome")
        if decision_by_id[decision_event_id].get("decision") == "NO_TRADE":
            raise ValueError("NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME")
        if not isinstance(row.get("closed_at"), str) or not row["closed_at"].strip():
            if outcome in CLOSED_OUTCOMES or outcome == "CANCELLED":
                raise ValueError("outcome_closed_at_required")
        elif outcome in CLOSED_OUTCOMES or outcome == "CANCELLED":
            try:
                closed = datetime.fromisoformat(row["closed_at"].replace("Z", "+00:00"))
                observed = datetime.fromisoformat(decision_by_id[decision_event_id]["observed_at"].replace("Z", "+00:00"))
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("invalid_outcome_timestamp") from exc
            if closed.tzinfo is None or observed.tzinfo is None:
                raise ValueError("outcome_timestamps_must_be_timezone_aware")
            if closed < observed:
                raise ValueError("outcome_precedes_decision")
        outcome_by_decision[decision_event_id] = row

    learning_rows = []
    for event_id, row in decision_by_id.items():
        outcome_row = outcome_by_decision.get(event_id)
        learning_rows.append({
            "event_id": event_id,
            "decision": row["decision"],
            "outcome": outcome_row.get("outcome") if outcome_row else None,
            "market_regime": row.get("market_regime", "UNKNOWN"),
            "rejected_at": row.get("rejected_at", ""),
            "decision_gate": row.get("decision_gate", ""),
            "source_period": "forward",
            "population": "forward",
        })
    return build_learning_report(learning_rows, min_group_size=min_group_size)



def record_forward_outcome(
    outcome_path: str | Path,
    *,
    decision_journal_path: str | Path,
    decision_event_id: str,
    outcome: str,
    closed_at: str | None,
    evidence_ref: str,
    evidence_sha256: str,
) -> JournalWriteResult:
    """Append an externally reconciled outcome; never calculate or infer PnL."""
    if outcome not in OUTCOME_VALUES:
        raise ValueError("invalid_outcome")
    if not isinstance(decision_event_id, str) or not decision_event_id.strip():
        raise ValueError("decision_event_id_required")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise ValueError("outcome_evidence_ref_required")
    if not isinstance(evidence_sha256, str) or len(evidence_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in evidence_sha256
    ):
        raise ValueError("invalid_outcome_evidence_sha256")
    if outcome in CLOSED_OUTCOMES or outcome == "CANCELLED":
        if not isinstance(closed_at, str) or not closed_at.strip():
            raise ValueError("outcome_closed_at_required")
    elif closed_at is not None:
        raise ValueError("open_outcome_must_not_have_closed_at")

    decision_path = Path(decision_journal_path)
    decisions = []
    for line in decision_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decisions.append(json.loads(line))
    matches = [row for row in decisions if row.get("event_id") == decision_event_id]
    if len(matches) != 1:
        raise ValueError("decision_event_not_found_or_ambiguous")
    decision = matches[0]
    if decision.get("artifact_type") != "FORWARD_OBSERVATION" or decision.get("artifact_kind") != "SIGNAL_DECISION":
        raise ValueError("decision_artifact_type_invalid")
    if decision.get("source_period") != "forward" or decision.get("execution") != "OFF":
        raise ValueError("decision_population_not_forward_only")
    if not isinstance(decision.get("digest"), str) or _digest_without_field(decision, "digest") != decision["digest"]:
        raise ValueError("decision_digest_mismatch")
    if decision.get("decision") == "NO_TRADE":
        raise ValueError("NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME")
    if decision.get("decision") not in {"LONG", "SHORT"}:
        raise ValueError("invalid_decision")
    if closed_at is not None:
        try:
            closed = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            observed = datetime.fromisoformat(decision["observed_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("invalid_outcome_timestamp") from exc
        if closed.tzinfo is None or observed.tzinfo is None:
            raise ValueError("outcome_timestamps_must_be_timezone_aware")
        if closed < observed:
            raise ValueError("outcome_precedes_decision")
    event_key = sha256(decision_event_id.encode("utf-8")).hexdigest()
    outcome_event_id = "outcome-" + event_key
    row = {
        "artifact_type": "FORWARD_OUTCOME",
        "outcome_event_id": outcome_event_id,
        "decision_event_id": decision_event_id,
        "outcome": outcome,
        "closed_at": closed_at,
        "source_period": "forward",
        "execution": "OFF",
        "evidence_ref": evidence_ref,
        "evidence_sha256": evidence_sha256,
        "decision_digest": decision["digest"],
    }
    row["digest"] = sha256(canonical_json(row).encode("utf-8")).hexdigest()
    path = Path(outcome_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    existing = json.loads(line)
                    if existing.get("outcome_event_id") == outcome_event_id:
                        if existing == row:
                            return JournalWriteResult("ALREADY_RECORDED", outcome_event_id, row["digest"])
                        raise ValueError("conflicting_duplicate_outcome_event")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(row) + "\\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    return JournalWriteResult("RECORDED", outcome_event_id, row["digest"])

def report_dict(report: LearningReport) -> dict:
    return asdict(report)
