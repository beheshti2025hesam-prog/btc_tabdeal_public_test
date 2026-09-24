"""
Mother Agent - Data Quality Contract
Data Foundation v1.0
"""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class DataQualityReport:
    """
    Stable summary of Data Foundation quality checks.

    integrity contains per-market integrity metrics.
    validation contains raw-row validation statistics.
    metadata is reserved for non-scoring audit context.
    """

    total_trades: int
    validation: Mapping[str, int] = field(default_factory=dict)
    integrity: Mapping[Any, Mapping[str, Any]] = field(
        default_factory=dict
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def has_integrity_issues(self) -> bool:
        """Return True when any tracked integrity anomaly exists."""

        issue_keys = (
            "duplicate_event_id_count",
            "duplicate_sequence_count",
            "sequence_gap_count",
            "backward_sequence_count",
            "timestamp_backward_count",
        )

        return any(
            report.get(key, 0) > 0
            for report in self.integrity.values()
            for key in issue_keys
        )

    @property
    def invalid_row_count(self) -> int:
        """Return the number of invalid raw rows, when supplied."""

        return int(self.validation.get("invalid_rows", 0))
