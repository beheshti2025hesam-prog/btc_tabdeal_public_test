"""
Tests for Mother Agent Raw Data Validator.
"""

from core.data_engine.validator import RawDataValidator


def valid_raw_row():
    return {
        "symbol": "BTC_USDT",
        "price": "100000.50",
        "amount": "0.001",
        "side": "buy",
        "updated": "2026-09-20T10:00:00Z",
        "sequence": "123456",
    }


def test_valid_row_has_no_errors():
    validator = RawDataValidator()

    errors = validator.validate_row(valid_raw_row())

    assert errors == []


def test_missing_required_column_is_detected():
    validator = RawDataValidator()

    row = valid_raw_row()
    del row["price"]

    errors = validator.validate_row(row)

    assert any("Missing columns" in error for error in errors)


def test_empty_symbol_is_detected():
    validator = RawDataValidator()

    row = valid_raw_row()
    row["symbol"] = ""

    errors = validator.validate_row(row)

    assert "Empty symbol" in errors


def test_invalid_price_is_detected():
    validator = RawDataValidator()

    row = valid_raw_row()
    row["price"] = "not-a-number"

    errors = validator.validate_row(row)

    assert "Invalid price" in errors


def test_invalid_amount_is_detected():
    validator = RawDataValidator()

    row = valid_raw_row()
    row["amount"] = "not-a-number"

    errors = validator.validate_row(row)

    assert "Invalid amount" in errors


def test_invalid_sequence_is_detected():
    validator = RawDataValidator()

    row = valid_raw_row()
    row["sequence"] = "not-an-integer"

    errors = validator.validate_row(row)

    assert "Invalid sequence" in errors


def test_validate_rows_returns_summary():
    validator = RawDataValidator()

    valid_row = valid_raw_row()

    invalid_row = valid_raw_row()
    invalid_row["price"] = "invalid"

    result = validator.validate_rows(
        [valid_row, invalid_row]
    )

    assert result == {
        "total_rows": 2,
        "valid_rows": 1,
        "invalid_rows": 1,
    }


def test_rejects_non_positive_or_non_finite_trade_values():
    validator = RawDataValidator()

    for value in ("0", "-1", "nan", "inf", "-inf"):
        row = valid_raw_row()
        row["price"] = value
        assert "Invalid price" in validator.validate_row(row)

        row = valid_raw_row()
        row["amount"] = value
        assert "Invalid amount" in validator.validate_row(row)


def test_rejects_invalid_or_naive_timestamp():
    validator = RawDataValidator()

    row = valid_raw_row()
    row["updated"] = "not-a-timestamp"
    assert "Invalid timestamp" in validator.validate_row(row)

    row = valid_raw_row()
    row["updated"] = "2026-09-20T10:00:00"
    assert "Timestamp must be timezone-aware" in validator.validate_row(row)


def test_rejects_non_positive_sequence():
    validator = RawDataValidator()
    for value in ("0", "-1"):
        row = valid_raw_row()
        row["sequence"] = value
        assert "Invalid sequence" in validator.validate_row(row)


def test_rejects_unknown_side():
    validator = RawDataValidator()
    row = valid_raw_row()
    row["side"] = "hold"
    assert "Invalid side" in validator.validate_row(row)
