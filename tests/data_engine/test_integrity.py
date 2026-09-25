"""
Tests for Mother Agent Data Integrity Audit.
"""

from datetime import datetime, timedelta, timezone

from core.data_engine.integrity import IntegrityAudit
from core.models.trade import CanonicalTrade


def trade(event_id, sequence, seconds, exchange="tabdeal", symbol="BTC_USDT"):
    return CanonicalTrade(
        event_id=event_id,
        source="test",
        exchange=exchange,
        symbol=symbol,
        price=100000.0,
        quantity=0.001,
        side="buy",
        timestamp=datetime(
            2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc
        ) + timedelta(seconds=seconds),
        sequence=sequence,
    )


def test_detects_sequence_gap_and_duplicate():
    result = IntegrityAudit().audit([
        trade("a", 1, 0),
        trade("b", 3, 1),
        trade("c", 3, 2),
    ])["groups"][("tabdeal", "BTC_USDT")]

    assert result["duplicate_sequence_count"] == 1
    assert result["sequence_gap_count"] == 1
    assert result["sequence_gap_total"] == 1
    assert result["largest_sequence_gap"] == 1
    assert result["min_sequence"] == 1
    assert result["max_sequence"] == 3


def test_detects_backward_sequence_in_timestamp_order():
    result = IntegrityAudit().audit([
        trade("a", 10, 0),
        trade("b", 8, 1),
        trade("c", 9, 2),
    ])["groups"][("tabdeal", "BTC_USDT")]

    assert result["backward_sequence_count"] == 1


def test_detects_timestamp_backward_in_sequence_order():
    result = IntegrityAudit().audit([
        trade("a", 10, 2),
        trade("b", 11, 1),
        trade("c", 12, 3),
    ])["groups"][("tabdeal", "BTC_USDT")]

    assert result["timestamp_backward_count"] == 1


def test_groups_markets_independently():
    result = IntegrityAudit().audit([
        trade("btc-1", 1, 0, symbol="BTC_USDT"),
        trade("sol-1", 1, 0, symbol="SOL_USDT"),
        trade("btc-2", 2, 1, symbol="BTC_USDT"),
    ])

    assert set(result["groups"]) == {
        ("tabdeal", "BTC_USDT"),
        ("tabdeal", "SOL_USDT"),
    }

    assert result["groups"][("tabdeal", "BTC_USDT")]["total_trades"] == 2
    assert result["groups"][("tabdeal", "SOL_USDT")]["total_trades"] == 1
