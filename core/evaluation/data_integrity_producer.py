"""Execution-free Data Integrity evidence producer.

Converts the existing DataQualityReport integrity section into one immutable
evidence result. It does not mutate raw data or make promotion decisions.
"""

from core.data_engine.quality import DataQualityReport
from core.evaluation.producer import EvidenceResult


class IntegrityEvidenceProducer:
    """Produce deterministic evidence from Data Foundation integrity results."""

    GATE_NAME = "data_integrity"

    @property
    def gate_name(self) -> str:
        return self.GATE_NAME

    def produce(self, context: object) -> EvidenceResult:
        if not isinstance(context, DataQualityReport):
            raise TypeError("IntegrityEvidenceProducer requires DataQualityReport")

        totals = {
            "duplicate_event_ids": 0,
            "duplicate_sequences": 0,
            "sequence_gaps": 0,
            "backward_sequences": 0,
            "timestamp_backward": 0,
        }
        for report in context.integrity.values():
            totals["duplicate_event_ids"] += int(report.get("duplicate_event_id_count", 0))
            totals["duplicate_sequences"] += int(report.get("duplicate_sequence_count", 0))
            totals["sequence_gaps"] += int(report.get("sequence_gap_count", 0))
            totals["backward_sequences"] += int(report.get("backward_sequence_count", 0))
            totals["timestamp_backward"] += int(report.get("timestamp_backward_count", 0))

        passed = all(value == 0 for value in totals.values())
        details = (
            f"duplicate_event_ids={totals['duplicate_event_ids']};"
            f"duplicate_sequences={totals['duplicate_sequences']};"
            f"sequence_gaps={totals['sequence_gaps']};"
            f"backward_sequences={totals['backward_sequences']};"
            f"timestamp_backward={totals['timestamp_backward']};"
            f"total_trades={context.total_trades}"
        )
        return EvidenceResult(self.GATE_NAME, passed, details)
