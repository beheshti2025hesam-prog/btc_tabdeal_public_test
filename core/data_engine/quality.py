"""
HES Trade Agent - Data Quality Contract.
"""
from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True)
class DataQualityReport:
    total_trades: int
    validation: Mapping[str, int] = field(default_factory=dict)
    integrity: Mapping[Any, Mapping[str, Any]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def has_integrity_issues(self) -> bool:
        keys = ("duplicate_event_id_count","duplicate_sequence_count","sequence_gap_count","backward_sequence_count","timestamp_backward_count")
        return any(report.get(key, 0) > 0 for report in self.integrity.values() for key in keys)

    @property
    def invalid_row_count(self) -> int:
        return int(self.validation.get("invalid_rows", 0))
