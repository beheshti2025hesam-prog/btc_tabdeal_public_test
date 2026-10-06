"""Safe self-improvement loop for HES POST-QUALITY-BASELINE.

The learning loop is deliberately proposal-only. It can learn from outcomes and
identify recurring failure patterns, but it never mutates live thresholds or
promotes a strategy from in-sample results. Promotion requires an independently
evaluated OOS candidate and an explicit approval step.
"""
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import Iterable, Literal


Outcome = Literal["win", "loss", "no_trade"]


@dataclass(frozen=True)
class OutcomeRecord:
    """Immutable result observed after a signal decision."""

    outcome: Outcome
    direction: str | None
    regime: str | None
    rejected_gate: str | None = None
    failure_codes: tuple[str, ...] = ()
    fold: int | None = None
    policy_version: str = "post-quality-baseline-v2"


@dataclass(frozen=True)
class ImprovementProposal:
    """A reviewable learning proposal; it is not a strategy mutation."""

    pattern: str
    support: int
    loss_count: int
    recommendation: str
    required_validation: str
    auto_promote: bool = False


@dataclass(frozen=True)
class PromotionCheck:
    """Explicit OOS evidence required before a proposal may be promoted."""

    candidate_id: str
    oos_evaluated: bool
    oos_independent: bool
    oos_improves_quality: bool
    no_material_risk_regression: bool
    approved: bool = False


class SelfImprovementEngine:
    """Mine recurring failure patterns without changing trading policy."""

    def __init__(self, min_support: int = 5):
        if min_support <= 0:
            raise ValueError("min_support must be positive")
        self.min_support = min_support

    def propose(self, records: Iterable[OutcomeRecord]) -> tuple[ImprovementProposal, ...]:
        records = tuple(records)
        patterns: dict[str, list[OutcomeRecord]] = defaultdict(list)

        for record in records:
            for code in record.failure_codes:
                patterns[f"failure:{code}"].append(record)
            if record.rejected_gate:
                patterns[f"gate:{record.rejected_gate}"].append(record)

        proposals: list[ImprovementProposal] = []
        for pattern, matched in patterns.items():
            if len(matched) < self.min_support:
                continue
            losses = sum(r.outcome == "loss" for r in matched)
            if losses == 0:
                continue

            proposals.append(
                ImprovementProposal(
                    pattern=pattern,
                    support=len(matched),
                    loss_count=losses,
                    recommendation=(
                        "Investigate this failure family and test a stricter "
                        "or better-defined evidence gate; do not alter live policy yet."
                    ),
                    required_validation=(
                        "Run a new candidate on untouched walk-forward/OOS data, "
                        "compare against the frozen POST-QUALITY policy, then require "
                        "explicit promotion approval."
                    ),
                )
            )

        return tuple(sorted(proposals, key=lambda p: (-p.loss_count, p.pattern)))

    @staticmethod
    def can_promote(check: PromotionCheck) -> bool:
        """Return True only when all independent OOS requirements are satisfied."""
        return (
            check.oos_evaluated
            and check.oos_independent
            and check.oos_improves_quality
            and check.no_material_risk_regression
            and check.approved
        )

    @staticmethod
    def summarize(records: Iterable[OutcomeRecord]) -> dict[str, int]:
        counts = Counter(r.outcome for r in records)
        return {
            "wins": counts["win"],
            "losses": counts["loss"],
            "no_trade": counts["no_trade"],
            "total": sum(counts.values()),
        }
