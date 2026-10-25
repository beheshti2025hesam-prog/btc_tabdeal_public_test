"""Evidence-only forward learning loop: attribution and hypothesis generation.

Consumes immutable forward decisions and separately recorded outcomes. This module
never changes strategy thresholds, execution state, or authorizes orders.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
import math

DECISIONS = frozenset({"LONG", "SHORT", "NO_TRADE"})
OUTCOMES = frozenset({None, "OPEN", "WIN", "LOSS", "BREAKEVEN", "CANCELLED"})
CLOSED_OUTCOMES = frozenset({"WIN", "LOSS", "BREAKEVEN"})


@dataclass(frozen=True)
class LearningReport:
    schema: str
    status: str
    source_record_count: int
    eligible_closed_trade_count: int
    excluded_unclosed_count: int
    decision_counts: dict[str, int]
    attribution: list[dict]
    hypotheses: list[dict]
    source_sha256: str


def _canonical_hash(rows: list[dict]) -> str:
    # Event IDs are unique, so sorting makes provenance independent of input order.
    canonical_rows = sorted(rows, key=lambda row: row["event_id"])
    payload = json.dumps(
        canonical_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _required_label(value: object, field: str, default: str) -> str:
    if value is None or value == "":
        return default
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    normalized = value.strip()
    if not normalized:
        return default
    if len(normalized) > 160:
        raise ValueError(f"invalid_{field}")
    return normalized


def build_learning_report(
    records: Iterable[Mapping], *, min_group_size: int = 5
) -> LearningReport:
    if isinstance(min_group_size, bool) or not isinstance(min_group_size, int) or min_group_size < 1:
        raise ValueError("min_group_size must be an integer >= 1")

    rows: list[dict] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("record_must_be_mapping")
        try:
            row = dict(record)
            # Ensure arbitrary values cannot produce a misleading provenance hash.
            json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("record_not_canonical_json") from exc
        rows.append(row)

    seen: set[str] = set()
    for row in rows:
        source_period = row.get("source_period")
        population = row.get("population")
        if (isinstance(source_period, str) and source_period.strip().lower() == "historical") or (
            isinstance(population, str) and population.strip().lower() in {"winner", "survivor"}
        ):
            raise ValueError("HISTORICAL_POPULATION_FORBIDDEN")

        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id != event_id.strip():
            raise ValueError("event_id_required")
        if event_id in seen:
            raise ValueError("duplicate_event_id")
        seen.add(event_id)

        decision = row.get("decision")
        outcome = row.get("outcome")
        if not isinstance(decision, str) or decision not in DECISIONS:
            raise ValueError("invalid_decision")
        if outcome is not None and (not isinstance(outcome, str) or outcome not in OUTCOMES):
            raise ValueError("invalid_outcome")
        if decision == "NO_TRADE" and outcome in CLOSED_OUTCOMES:
            raise ValueError("NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME")

        # Validate attribution dimensions before string conversion; never stringify
        # dicts/lists into apparently legitimate market regimes or gate names.
        _required_label(row.get("market_regime"), "market_regime", "UNKNOWN")
        _required_label(row.get("rejected_at"), "rejected_at", "")
        _required_label(row.get("decision_gate"), "decision_gate", "")

    counts = Counter(row["decision"] for row in rows)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        outcome = row.get("outcome")
        regime = _required_label(row.get("market_regime"), "market_regime", "UNKNOWN")
        rejected_at = _required_label(row.get("rejected_at"), "rejected_at", "")
        decision_gate = _required_label(row.get("decision_gate"), "decision_gate", "")
        gate = rejected_at or decision_gate or "UNSPECIFIED"

        if row["decision"] == "NO_TRADE":
            groups[(gate, "NO_TRADE")].append(row)
        elif outcome in CLOSED_OUTCOMES:
            groups[(f"GATE:{gate}", outcome)].append(row)
            groups[(f"REGIME:{regime}", outcome)].append(row)

    attribution = []
    for (dimension, outcome), items in sorted(groups.items()):
        attribution.append({
            "dimension": dimension,
            "outcome": outcome,
            "count": len(items),
            "event_ids_sha256": sha256(
                "\n".join(sorted(item["event_id"] for item in items)).encode("utf-8")
            ).hexdigest(),
        })

    hypotheses = []
    for dimension in sorted({dimension for dimension, _ in groups}):
        losses = len(groups.get((dimension, "LOSS"), []))
        wins = len(groups.get((dimension, "WIN"), []))
        breakevens = len(groups.get((dimension, "BREAKEVEN"), []))
        closed = losses + wins + breakevens
        if closed >= min_group_size and losses > wins:
            hypotheses.append({
                "type": "INVESTIGATE_LOSS_CONCENTRATION",
                "dimension": dimension,
                "closed_count": closed,
                "loss_count": losses,
                "win_count": wins,
                "breakeven_count": breakevens,
                "action": "RESEARCH_ONLY_NO_PARAMETER_CHANGE",
            })

    closed_count = sum(
        row.get("outcome") in CLOSED_OUTCOMES and row["decision"] in {"LONG", "SHORT"}
        for row in rows
    )
    # Cancelled trades are neither closed performance outcomes nor open trades.
    unclosed = sum(
        row["decision"] in {"LONG", "SHORT"}
        and row.get("outcome") in {None, "OPEN"}
        for row in rows
    )
    return LearningReport(
        "hes_forward_learning_loop_v1",
        "DESCRIPTIVE_ONLY_HYPOTHESES_NOT_ACTIONS",
        len(rows),
        closed_count,
        unclosed,
        {key: counts.get(key, 0) for key in ("LONG", "SHORT", "NO_TRADE")},
        attribution,
        hypotheses,
        _canonical_hash(rows),
    )


def report_json(report: LearningReport) -> str:
    return json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False)



@dataclass(frozen=True)
class ForwardEvidenceRun:
    """Learning report plus hashes and validated rows from existing forward inputs."""
    report: LearningReport
    evidence_manifest: dict
    rows: tuple[dict, ...] = ()


def _strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non_finite_json_constant:{value}")


def _read_json_bytes(raw: bytes, *, error_code: str):
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(error_code) from exc


def _aware_timestamp(value, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def build_report_from_forward_evidence(
    journal_path: str | Path,
    outcome_dir: str | Path,
    *,
    now: datetime | None = None,
    min_group_size: int = 5,
) -> ForwardEvidenceRun:
    """Read the existing append-only decision journal and immutable outcome artifacts.

    The original decision rows are never rewritten. An outcome is joined by event_id
    only after validation against the existing runtime outcome contract. Missing
    outcomes remain missing; no result is inferred from price candles or decisions.
    """
    from .forward_runtime_validation_v1 import (
        validate_decision_record,
        validate_outcome_artifact,
    )

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now_must_be_timezone_aware")
    current = current.astimezone(timezone.utc)

    journal = Path(journal_path)
    outcomes_root = Path(outcome_dir)
    if journal.is_symlink() or not journal.is_file():
        raise ValueError("FORWARD_DECISION_JOURNAL_MISSING_OR_UNSAFE")
    if outcomes_root.is_symlink() or not outcomes_root.is_dir():
        raise ValueError("FORWARD_OUTCOME_DIRECTORY_MISSING_OR_UNSAFE")

    journal_bytes = journal.read_bytes()
    if not journal_bytes:
        raise ValueError("FORWARD_DECISION_JOURNAL_EMPTY")
    try:
        journal_text = journal_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("FORWARD_DECISION_JOURNAL_NOT_UTF8") from exc
    if not journal_text.endswith("\n"):
        raise ValueError("FORWARD_DECISION_JOURNAL_PARTIAL_TAIL")

    decisions = []
    seen_ids = set()
    for line_no, line in enumerate(journal_text.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"FORWARD_DECISION_JOURNAL_BLANK_LINE:{line_no}")
        row = _read_json_bytes(line.encode("utf-8"), error_code=f"FORWARD_DECISION_JSON_INVALID:{line_no}")
        if not isinstance(row, dict):
            raise ValueError(f"FORWARD_DECISION_RECORD_NOT_OBJECT:{line_no}")
        required = {"event_id", "observed_at", "symbol", "timeframe", "decision", "evidence_source"}
        if not required.issubset(row):
            raise ValueError(f"FORWARD_DECISION_REQUIRED_FIELDS_MISSING:{line_no}")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in seen_ids:
            raise ValueError(f"FORWARD_DECISION_EVENT_ID_INVALID_OR_DUPLICATE:{line_no}")
        seen_ids.add(event_id)
        if not isinstance(row.get("decision"), str) or row.get("decision") not in DECISIONS:
            raise ValueError(f"FORWARD_DECISION_INVALID:{line_no}")
        if row.get("outcome") is not None:
            raise ValueError(f"FORWARD_DECISION_HAS_OUTCOME:{line_no}")
        errors = validate_decision_record(row)
        if errors:
            raise ValueError(f"FORWARD_DECISION_RECORD_REJECTED:{line_no}:{','.join(errors)}")
        if row.get("closed_at") is not None:
            raise ValueError(f"FORWARD_DECISION_HAS_MUTABLE_OUTCOME_FIELDS:{line_no}")
        observed = _aware_timestamp(row.get("observed_at"), field="observed_at")
        if observed > current:
            raise ValueError(f"FORWARD_DECISION_FROM_FUTURE:{line_no}")
        row = dict(row)
        row["outcome"] = None
        row["closed_at"] = None
        decisions.append(row)

    if not decisions:
        raise ValueError("FORWARD_DECISION_JOURNAL_HAS_NO_RECORDS")

    decision_by_id = {row["event_id"]: row for row in decisions}
    outcome_files = sorted(outcomes_root.glob("*.json"), key=lambda p: p.name)
    outcome_hashes = []
    outcome_sha_by_id = {}
    outcome_by_id = {}
    for path in outcome_files:
        if path.is_symlink() or not path.is_file():
            raise ValueError("FORWARD_OUTCOME_ARTIFACT_UNSAFE_PATH")
        raw = path.read_bytes()
        artifact = _read_json_bytes(raw, error_code=f"FORWARD_OUTCOME_ARTIFACT_INVALID:{path.name}")
        if not isinstance(artifact, dict):
            raise ValueError(f"FORWARD_OUTCOME_ARTIFACT_NOT_OBJECT:{path.name}")
        event_id = artifact.get("event_id")
        if not isinstance(artifact.get("outcome"), str) or artifact.get("outcome") not in {"WIN", "LOSS", "BREAKEVEN", "CANCELLED"}:
            raise ValueError(f"FORWARD_OUTCOME_INVALID:{path.name}")
        errors = validate_outcome_artifact(artifact, decision_event_ids=set(decision_by_id))
        if errors:
            raise ValueError(f"FORWARD_OUTCOME_ARTIFACT_REJECTED:{path.name}:{','.join(errors)}")
        if event_id in outcome_by_id:
            raise ValueError(f"FORWARD_OUTCOME_DUPLICATE_EVENT_ID:{event_id}")
        decision = decision_by_id[event_id]
        if decision["decision"] not in {"LONG", "SHORT"}:
            raise ValueError(f"FORWARD_OUTCOME_FOR_NON_TRADE_DECISION:{event_id}")
        source_period = artifact.get("source_period")
        population = artifact.get("population")
        if (isinstance(source_period, str) and source_period.strip().lower() == "historical") or (
            isinstance(population, str) and population.strip().lower() in {"winner", "survivor"}
        ):
            raise ValueError("HISTORICAL_OR_SURVIVOR_OUTCOME_FORBIDDEN")
        closed_at = _aware_timestamp(artifact.get("closed_at"), field="closed_at")
        observed_at = _aware_timestamp(decision["observed_at"], field="observed_at")
        if closed_at <= observed_at or closed_at > current:
            raise ValueError(f"FORWARD_OUTCOME_CLOSE_TIME_INVALID:{event_id}")
        if "realized_rr" in artifact and artifact["realized_rr"] is not None:
            rr = artifact["realized_rr"]
            if isinstance(rr, bool) or not isinstance(rr, (int, float)) or not math.isfinite(rr):
                raise ValueError(f"FORWARD_OUTCOME_REALIZED_RR_INVALID:{event_id}")
        outcome_by_id[event_id] = artifact
        artifact_sha = sha256(raw).hexdigest()
        outcome_sha_by_id[event_id] = artifact_sha
        outcome_hashes.append({"file": path.name, "event_id": event_id, "sha256": artifact_sha})

    merged = []
    for row in decisions:
        combined = dict(row)
        artifact = outcome_by_id.get(row["event_id"])
        if artifact is not None:
            combined["outcome"] = artifact["outcome"]
            combined["closed_at"] = artifact["closed_at"]
            if artifact.get("realized_rr") is not None:
                combined["realized_rr"] = artifact["realized_rr"]
            combined["outcome_artifact_sha256"] = outcome_sha_by_id[row["event_id"]]
        merged.append(combined)

    outcome_manifest_payload = json.dumps(
        outcome_hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    manifest = {
        "schema": "hes_forward_learning_evidence_manifest_v1",
        "status": "EVIDENCE_READ_ONLY_REPORT",
        "decision_journal_sha256": sha256(journal_bytes).hexdigest(),
        "decision_record_count": len(decisions),
        "outcome_artifact_count": len(outcome_hashes),
        "outcome_manifest_sha256": sha256(outcome_manifest_payload).hexdigest(),
        "outcome_artifacts": outcome_hashes,
        "historical_inputs_allowed": False,
        "decision_rows_mutated": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    report = build_learning_report(merged, min_group_size=min_group_size)
    return ForwardEvidenceRun(report=report, evidence_manifest=manifest, rows=tuple(merged))
