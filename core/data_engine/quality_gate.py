"""
Mother Agent - Data Quality Gate
Data Foundation v1.0

Policy-driven, deterministic gate over a DataQualityReport.
The gate never mutates data and does not score or rank quality.
"""

from dataclasses import dataclass

from core.data_engine.quality import DataQualityReport


@dataclass(frozen=True)
class QualityGatePolicy:
    """Explicit thresholds for accepting a quality report."""

    max_invalid_rows: int = 0
    max_duplicate_event_ids: int = 0
    max_duplicate_sequences: int = 0
    max_sequence_gaps: int = 0
    max_backward_sequences: int = 0
    max_timestamp_backwards: int = 0


@dataclass(frozen=True)
class QualityGateResult:
    """Deterministic gate decision and the violated rules."""

    passed: bool
    violations: tuple[str, ...]

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "REJECT"


class DataQualityGate:
    """Apply an explicit policy to a DataQualityReport."""

    def __init__(self, policy: QualityGatePolicy | None = None):
        self.policy = policy or QualityGatePolicy()

    def evaluate(self, report: DataQualityReport) -> QualityGateResult:
        violations: list[str] = []

        if report.invalid_row_count > self.policy.max_invalid_rows:
            violations.append("invalid_rows")

        for group in report.integrity.values():
            checks = (
                (
                    "duplicate_event_ids",
                    "duplicate_event_id_count",
                    self.policy.max_duplicate_event_ids,
                ),
                (
                    "duplicate_sequences",
                    "duplicate_sequence_count",
                    self.policy.max_duplicate_sequences,
                ),
                (
                    "sequence_gaps",
                    "sequence_gap_count",
                    self.policy.max_sequence_gaps,
                ),
                (
                    "backward_sequences",
                    "backward_sequence_count",
                    self.policy.max_backward_sequences,
                ),
                (
                    "timestamp_backwards",
                    "timestamp_backward_count",
                    self.policy.max_timestamp_backwards,
                ),
            )

            for name, key, maximum in checks:
                if group.get(key, 0) > maximum:
                    violations.append(name)

        return QualityGateResult(
            passed=not violations,
            violations=tuple(violations),
        )
