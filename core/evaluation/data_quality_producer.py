"""Execution-free Data Quality evidence producer.

Converts an existing DataQualityReport into one immutable evidence result.
It does not alter raw data, infer missing trades, choose trading thresholds,
or make promotion decisions.
"""

from core.data_engine.quality import DataQualityReport
from core.evaluation.producer import EvidenceResult


class DataQualityEvidenceProducer:
    """Produce deterministic evidence from the Data Foundation quality report."""

    GATE_NAME = "data_quality"

    @property
    def gate_name(self) -> str:
        return self.GATE_NAME

    def produce(self, context: object) -> EvidenceResult:
        if not isinstance(context, DataQualityReport):
            raise TypeError("DataQualityEvidenceProducer requires DataQualityReport")

        invalid_rows = context.invalid_row_count
        integrity_issues = context.has_integrity_issues
        passed = invalid_rows == 0 and not integrity_issues

        details = (
            f"invalid_rows={invalid_rows};"
            f"integrity_issues={integrity_issues};"
            f"total_trades={context.total_trades}"
        )
        return EvidenceResult(self.GATE_NAME, passed, details)
