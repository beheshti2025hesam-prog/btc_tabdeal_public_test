"""
Tests for DataEngine quality integration.
"""

from datetime import datetime, timezone

from core.data_engine.engine import DataEngine
from core.models.trade import CanonicalTrade


class FakeReader:
    def read_all(self):
        return [
            {
                "symbol": "BTC_USDT",
                "price": "100000",
                "amount": "0.001",
                "side": "buy",
                "updated": "2026-09-20T10:00:00+00:00",
                "sequence": "1",
            },
            {
                "symbol": "BTC_USDT",
                "price": "100001",
                "amount": "0.002",
                "side": "buy",
                "updated": "2026-09-20T10:00:01+00:00",
                "sequence": "3",
            },
            {
                "symbol": "BTC_USDT",
                "price": "100002",
                "amount": "0.003",
                "side": "sell",
                "updated": "2026-09-20T10:00:02+00:00",
                "sequence": "3",
            },
        ]


def test_engine_produces_quality_report():
    engine = DataEngine(reader=FakeReader())

    trades = engine.load()
    report = engine.last_quality_report

    assert len(trades) == 3
    assert report is not None

    assert report.total_trades == 3
    assert report.validation["total_rows"] == 3
    assert report.validation["valid_rows"] == 3
    assert report.validation["invalid_rows"] == 0

    assert report.has_integrity_issues is True

    group = report.integrity[("tabdeal", "BTC_USDT")]

    assert group["duplicate_sequence_count"] == 1
    assert group["sequence_gap_count"] == 1


def test_engine_quality_report_is_created_before_deduplication():
    engine = DataEngine(reader=FakeReader())

    engine.load()

    report = engine.last_quality_report

    assert report is not None
    assert report.total_trades == 3
    assert report.metadata["deduplicated_trades"] == 3
