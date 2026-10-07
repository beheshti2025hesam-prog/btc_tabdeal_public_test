"""Forward-only opportunity candidate primitives.

Candidate generation is intentionally separated from confirmation, risk and
execution. This reference implementation fails closed unless an explicit,
versioned opportunity policy is supplied by the caller.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Sequence

CandidateState = Literal["CANDIDATE_LONG","CANDIDATE_SHORT","NO_CANDIDATE"]

@dataclass(frozen=True)
class OpportunityCandidate:
    observed_at: object
    symbol: str
    timeframe: str
    state: CandidateState
    regime: str
    structure_labels: tuple[str, ...]
    structure_events: tuple[str, ...]
    reason_codes: tuple[str, ...]
    quality_score: float | None = None

class OpportunityDetectorV1:
    """Contract boundary; no hidden strategy thresholds."""

    def __init__(self, policy=None):
        self.policy = policy

    def evaluate(
        self,
        *,
        observed_at,
        symbol: str,
        timeframe: str,
        regime: str,
        structure_labels: Sequence[str] = (),
        structure_events: Sequence[str] = (),
    ) -> OpportunityCandidate:
        if self.policy is None:
            return OpportunityCandidate(
                observed_at=observed_at,
                symbol=symbol,
                timeframe=timeframe,
                state="NO_CANDIDATE",
                regime=regime,
                structure_labels=tuple(structure_labels),
                structure_events=tuple(structure_events),
                reason_codes=("NO_POLICY_CONFIGURED",),
            )
        result = self.policy.evaluate(
            observed_at=observed_at,
            symbol=symbol,
            timeframe=timeframe,
            regime=regime,
            structure_labels=tuple(structure_labels),
            structure_events=tuple(structure_events),
        )
        if not isinstance(result, OpportunityCandidate):
            raise TypeError("Opportunity policy must return OpportunityCandidate")
        return result
