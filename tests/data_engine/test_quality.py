"""
Tests for the Mother Agent Data Quality report contract.
"""

from core.data_engine.quality import DataQualityReport


def test_quality_report_defaults_are_safe():
    report = DataQualityReport(total_trades=10)

    assert report.validation == {}
    assert report.integrity == {}
    assert report.metadata == {}
    assert report.invalid_row_count == 0
    assert report.has_integrity_issues is False


def test_quality_report_detects_integrity_issue():
    report = DataQualityReport(
        total_trades=3,
        integrity={
            ("tabdeal", "BTC_USDT"): {
                "duplicate_sequence_count": 1,
            }
        },
    )

    assert report.has_integrity_issues is True


def test_quality_report_exposes_invalid_rows():
    report = DataQualityReport(
        total_trades=2,
        validation={
            "total_rows": 3,
            "valid_rows": 2,
            "invalid_rows": 1,
        },
    )

    assert report.invalid_row_count == 1
