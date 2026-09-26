"""Execution-free evidence aggregation contract.

Combines immutable producer results into one evidence snapshot for a single
project identity and source commit. It does not choose thresholds, rank
strategies, promote deployments, or execute trades.
"""

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.producer import EvidenceResult


class EvidenceAggregator:
    """Build one immutable evidence snapshot from producer results."""

    PROJECT_NAME = "HES Trade Agent"
    OWNER = "Seyed Hesameddin Beheshti Shirazi"

    def build(
        self,
        source_commit: str,
        results: tuple[EvidenceResult, ...],
    ) -> EvidenceSnapshot:
        if not isinstance(source_commit, str) or not source_commit.strip():
            raise ValueError("source_commit must be non-empty")
        if not results:
            raise ValueError("evidence results must not be empty")

        evidence: dict[str, bool] = {}
        for result in results:
            if result.gate_name in evidence:
                raise ValueError("duplicate evidence gate")
            evidence[result.gate_name] = result.passed

        return EvidenceSnapshot.create(
            self.PROJECT_NAME,
            self.OWNER,
            source_commit,
            evidence,
        )
