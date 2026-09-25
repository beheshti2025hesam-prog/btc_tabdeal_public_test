"""
Tests for Mother Agent Raw Data Normalizer.
"""

import pytest

from core.data_engine.normalizer import RawDataNormalizer
from core.models.trade import CanonicalTrade


def valid_raw_row():
    return {
        "symbol": "BTC_USDT",
        "price": "100000.50",
        "amount": "0.001",
        "side": "buy",
        "updated": "2026-09-20T10:00:00Z",
        "sequence": "123456",
    }


def test_normalizer_returns_canonical_trade():
    normalizer = RawDataNormalizer(source="raw_csv", exchange="tabdeal")

    trade = normalizer.normalize_row(valid_raw_row())

    assert isinstance(trade, CanonicalTrade)
    assert trade.symbol == "BTC_USDT"
    assert trade.price == 100000.50
    assert trade.quantity == 0.001
    assert trade.side == "buy"
    assert trade.sequence == 123456
    assert trade.source == "raw_csv"
    assert trade.exchange == "tabdeal"
    assert trade.ingested_at is None


def test_provenance_is_configurable():
    normalizer = RawDataNormalizer(
        source="normalized_stream",
        exchange="example_exchange",
    )

    trade = normalizer.normalize_row(valid_raw_row())

    assert trade.source == "normalized_stream"
    assert trade.exchange == "example_exchange"


def test_empty_provenance_is_rejected():
    with pytest.raises(ValueError, match="source must not be empty"):
        RawDataNormalizer(source="", exchange="tabdeal")

    with pytest.raises(ValueError, match="exchange must not be empty"):
        RawDataNormalizer(source="raw_csv", exchange="")


def test_normalizer_converts_z_timestamp_to_timezone_aware_utc():
    normalizer = RawDataNormalizer()

    trade = normalizer.normalize_row(valid_raw_row())

    assert trade.timestamp.tzinfo is not None
    assert trade.timestamp.utcoffset().total_seconds() == 0


def test_event_id_is_deterministic():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()

    trade_1 = normalizer.normalize_row(row)
    trade_2 = normalizer.normalize_row(row)

    assert trade_1.event_id == trade_2.event_id


def test_invalid_price_raises_error():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()
    row["price"] = "not-a-number"

    with pytest.raises(ValueError, match="Invalid price"):
        normalizer.normalize_row(row)


def test_invalid_amount_raises_error():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()
    row["amount"] = "not-a-number"

    with pytest.raises(ValueError, match="Invalid amount"):
        normalizer.normalize_row(row)


def test_invalid_sequence_raises_error():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()
    row["sequence"] = "not-an-integer"

    with pytest.raises(ValueError, match="Invalid sequence"):
        normalizer.normalize_row(row)


def test_invalid_timestamp_raises_error():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()
    row["updated"] = "not-a-timestamp"

    with pytest.raises(ValueError, match="Invalid timestamp"):
        normalizer.normalize_row(row)


def test_normalizer_does_not_modify_input_row():
    normalizer = RawDataNormalizer()

    row = valid_raw_row()
    original_row = row.copy()

    normalizer.normalize_row(row)

    assert row == original_row


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_invalid_non_positive_or_non_finite_price_raises(value):
    row = valid_raw_row()
    row["price"] = value

    with pytest.raises(ValueError, match="Invalid price"):
        RawDataNormalizer().normalize_row(row)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_invalid_non_positive_or_non_finite_amount_raises(value):
    row = valid_raw_row()
    row["amount"] = value

    with pytest.raises(ValueError, match="Invalid amount"):
        RawDataNormalizer().normalize_row(row)
