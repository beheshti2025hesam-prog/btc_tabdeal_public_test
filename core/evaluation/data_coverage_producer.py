"""Execution-free Coverage evidence producer.

Coverage is treated as explicit evidence input. Sequence gaps alone are not
interpreted as confirmed market-data loss.
"""

from core.data_engine.quality import DataQualityReport
from core.evaluation.producer import EvidenceResult


class CoverageEvidenceProducer:
    """Produce deterministic coverage evidence without inferring data loss."""

    GATE_NAME = "coverage"

    @property
    def gate_name(self) -> str:
        return self.GATE_NAME

    def produce(self, context: object) -> EvidenceResult:
        if not isinstance(context, DataQualityReport):
            raise TypeError("CoverageEvidenceProducer requires DataQualityReport")

        declared_gaps = int(context.metadata.get("declared_coverage_gaps", 0))
        confirmed_gaps = int(context.metadata.get("confirmed_coverage_gaps", 0))
        if declared_gaps < 0 or confirmed_gaps < 0 or confirmed_gaps > declared_gaps:
            raise ValueError("coverage metadata is invalid")

        passed = confirmed_gaps == 0
        details = (
            f"declared_coverage_gaps={declared_gaps};"
            f"confirmed_coverage_gaps={confirmed_gaps};"
            "sequence_gaps_are_not_confirmed_coverage_loss=true"
        )
        return EvidenceResult(self.GATE_NAME, passed, details)
