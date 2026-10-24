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
        if outcome not in OUTCOMES:
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
