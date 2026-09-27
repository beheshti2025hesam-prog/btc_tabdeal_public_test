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
        integrity_issue_count = 0
        sequence_gap_count = 0
        for report in context.integrity.values():
            integrity_issue_count += int(report.get("duplicate_event_id_count", 0))
            integrity_issue_count += int(report.get("duplicate_sequence_count", 0))
            integrity_issue_count += int(report.get("backward_sequence_count", 0))
            integrity_issue_count += int(report.get("timestamp_backward_count", 0))
            sequence_gap_count += int(report.get("sequence_gap_count", 0))

        passed = invalid_rows == 0 and integrity_issue_count == 0

        details = (
            f"invalid_rows={invalid_rows};"
            f"integrity_issues={integrity_issue_count > 0};"
            f"sequence_gaps={sequence_gap_count};"
            "sequence_gaps_are_anomalies_not_confirmed_loss=true;"
            f"total_trades={context.total_trades}"
        )
        return EvidenceResult(self.GATE_NAME, passed, details)
