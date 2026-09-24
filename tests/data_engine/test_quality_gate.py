"""
Tests for the Mother Agent Data Quality Gate.
"""

from core.data_engine.quality import DataQualityReport
from core.data_engine.quality_gate import (
    DataQualityGate,
    QualityGatePolicy,
)


def test_quality_gate_passes_clean_report():
    report = DataQualityReport(
        total_trades=10,
        validation={
            "total_rows": 10,
            "valid_rows": 10,
            "invalid_rows": 0,
        },
        integrity={
            ("tabdeal", "BTC_USDT"): {
                "duplicate_event_id_count": 0,
                "duplicate_sequence_count": 0,
                "sequence_gap_count": 0,
                "backward_sequence_count": 0,
                "timestamp_backward_count": 0,
            }
        },
    )

    result = DataQualityGate().evaluate(report)

    assert result.passed is True
    assert result.status == "PASS"
    assert result.violations == ()


def test_quality_gate_rejects_integrity_violations():
    report = DataQualityReport(
        total_trades=3,
        integrity={
            ("tabdeal", "BTC_USDT"): {
                "duplicate_sequence_count": 1,
                "sequence_gap_count": 1,
            }
        },
    )

    result = DataQualityGate().evaluate(report)

    assert result.passed is False
    assert result.status == "REJECT"
    assert result.violations == (
        "duplicate_sequences",
        "sequence_gaps",
    )


def test_quality_gate_rejects_invalid_rows_by_default():
    report = DataQualityReport(
        total_trades=2,
        validation={"invalid_rows": 1},
    )

    result = DataQualityGate().evaluate(report)

    assert result.passed is False
    assert result.violations == ("invalid_rows",)


def test_quality_gate_supports_explicit_tolerances():
    report = DataQualityReport(
        total_trades=100,
        validation={"invalid_rows": 1},
        integrity={
            ("tabdeal", "BTC_USDT"): {
                "duplicate_event_id_count": 1,
                "sequence_gap_count": 2,
            }
        },
    )

    policy = QualityGatePolicy(
        max_invalid_rows=1,
        max_duplicate_event_ids=1,
        max_sequence_gaps=2,
    )

    result = DataQualityGate(policy).evaluate(report)

    assert result.passed is True
    assert result.status == "PASS"
