"""Evidence-only forward learning loop: attribution and hypothesis generation.

Never changes strategy thresholds or authorizes execution. Uses immutable forward
decisions and separately attached closed outcomes; proposals require human review.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable, Mapping

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
    return sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def build_learning_report(records: Iterable[Mapping], *, min_group_size: int = 5) -> LearningReport:
    if min_group_size < 1:
        raise ValueError("min_group_size must be >= 1")
    rows = [dict(r) for r in records]
    seen: set[str] = set()
    for row in rows:
        if row.get("source_period") == "historical" or row.get("population") in {"Winner", "Survivor"}:
            raise ValueError("HISTORICAL_POPULATION_FORBIDDEN")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id_required")
        if event_id in seen:
            raise ValueError("duplicate_event_id")
        seen.add(event_id)
        if row.get("decision") not in {"LONG", "SHORT", "NO_TRADE"}:
            raise ValueError("invalid_decision")
        if row.get("outcome") not in {None, "OPEN", "WIN", "LOSS", "BREAKEVEN", "CANCELLED"}:
            raise ValueError("invalid_outcome")
        if row.get("decision") == "NO_TRADE" and row.get("outcome") in {"WIN", "LOSS", "BREAKEVEN"}:
            raise ValueError("NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME")
    counts = Counter(r["decision"] for r in rows)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        outcome = row.get("outcome")
        regime = str(row.get("market_regime") or "UNKNOWN")
        gate = str(row.get("rejected_at") or row.get("decision_gate") or "UNSPECIFIED")
        if row["decision"] == "NO_TRADE":
            groups[(gate, "NO_TRADE")].append(row)
        elif outcome in {"WIN", "LOSS", "BREAKEVEN"}:
            groups[(gate, str(outcome))].append(row)
            groups[("REGIME:" + regime, str(outcome))].append(row)
    attribution = []
    for (dimension, outcome), items in sorted(groups.items()):
        attribution.append({"dimension": dimension, "outcome": outcome, "count": len(items),
            "event_ids_sha256": sha256("\n".join(sorted(x["event_id"] for x in items)).encode()).hexdigest()})
    hypotheses = []
    for dimension in sorted({d for d, _ in groups}):
        losses, wins = len(groups.get((dimension, "LOSS"), [])), len(groups.get((dimension, "WIN"), []))
        closed = losses + wins + len(groups.get((dimension, "BREAKEVEN"), []))
        if closed >= min_group_size and losses > wins:
            hypotheses.append({"type": "INVESTIGATE_LOSS_CONCENTRATION", "dimension": dimension,
                "closed_count": closed, "loss_count": losses, "win_count": wins,
                "action": "RESEARCH_ONLY_NO_PARAMETER_CHANGE"})
    closed_count = sum(r.get("outcome") in {"WIN", "LOSS", "BREAKEVEN"} and r["decision"] in {"LONG", "SHORT"} for r in rows)
    unclosed = sum(r["decision"] in {"LONG", "SHORT"} and r.get("outcome") not in {"WIN", "LOSS", "BREAKEVEN", "CANCELLED"} for r in rows)
    return LearningReport("hes_forward_learning_loop_v1", "DESCRIPTIVE_ONLY_HYPOTHESES_NOT_ACTIONS",
        len(rows), closed_count, unclosed, {k: counts.get(k, 0) for k in ("LONG", "SHORT", "NO_TRADE")},
        attribution, hypotheses, _canonical_hash(rows))

def report_json(report: LearningReport) -> str:
    return json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
