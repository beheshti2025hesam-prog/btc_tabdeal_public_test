from decimal import Decimal

import pytest

from core.paper.tabdeal_fapi_fee_reconciliation_v1 import (
    FeeObservationError,
    build_historical_fee_observation,
)


def trades():
    return [
        {
            "symbol": "BTCUSDT", "id": 2001, "orderId": 5001,
            "price": "39700.00", "qty": "0.1", "quoteQty": "3970.00",
            "commission": "3.97", "commissionAsset": "USDT",
            "time": 1660046774413, "buyer": True, "maker": False,
        },
        {
            "symbol": "BTCUSDT", "id": 2002, "orderId": 5002,
            "price": "40000.00", "qty": "0.01", "quoteQty": "400.00",
            "commission": "0.00001", "commissionAsset": "BTC",
            "time": 1660046775413, "buyer": False, "maker": True,
        },
        {
            "symbol": "BTCUSDT", "id": 2003, "orderId": 5003,
            "price": "40100.00", "qty": "0.01", "quoteQty": "401.00",
            "commission": "0.2", "commissionAsset": "BNB",
            "time": 1660046776413, "buyer": False, "maker": True,
        },
    ]


def income():
    return [
        {
            "symbol": "BTCUSDT", "incomeType": "TakerCommission",
            "income": "-3.97", "asset": "USDT", "time": 1660046774413,
        },
        {
            "symbol": "BTCUSDT", "incomeType": "MakerCommission",
            "income": "-0.00001", "asset": "BTC", "time": 1660046775413,
        },
        {
            "symbol": "", "incomeType": "Transfer",
            "income": "10.00", "asset": "USDT", "time": 1660046777413,
        },
    ]


def test_historical_fee_observation_converts_only_quote_and_base_assets():
    report = build_historical_fee_observation(
        trades(), income(), expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert report.status == "HISTORICAL_OBSERVATION_ONLY"
    assert report.trade_count == 3
    assert report.maker_trade_count == 2
    assert report.taker_trade_count == 1
    assert report.quote_comparable_trade_count == 2
    assert report.unpriced_commission_trade_count == 1
    assert Decimal(report.total_quote_notional) == Decimal("4370.00")
    assert Decimal(report.total_quote_equivalent_commission) == Decimal("4.37")
    assert Decimal(report.weighted_fee_bps) == Decimal("10")
    assert Decimal(report.trades[1].commission_quote_equivalent) == Decimal("0.4")
    assert report.trades[2].commission_quote_equivalent is None
    assert report.fee_schedule_verified is False
    assert report.future_fee_tier_verified is False
    assert report.execution_enabled is False
    assert report.orders_placed is False


def test_income_rows_are_preserved_and_summarized_without_deduplication():
    rows = income() + [dict(income()[0])]
    report = build_historical_fee_observation(
        trades(), rows, expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert len(report.income_rows) == 4
    summary = {
        (kind, asset): (amount, count)
        for kind, asset, amount, count in report.income_by_type_and_asset
    }
    assert summary[("TakerCommission", "USDT")] == ("-7.94", 2)
    assert report.income_trade_reconciliation.startswith("NOT_PERFORMED_")


def test_exact_symbol_is_required_no_alias_normalization():
    with pytest.raises(FeeObservationError, match="SYMBOL_MISMATCH"):
        build_historical_fee_observation(
            trades(), income(), expected_symbol="BTC_USDT",
            base_asset="BTC", quote_asset="USDT",
        )


@pytest.mark.parametrize("field,value", [
    ("maker", 1), ("time", True), ("commission", "NaN"),
    ("quoteQty", "0"), ("commissionAsset", ""),
])
def test_invalid_trade_fields_fail_closed(field, value):
    rows = trades()
    rows[0][field] = value
    with pytest.raises(FeeObservationError):
        build_historical_fee_observation(
            rows, income(), expected_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
        )


def test_unknown_commission_asset_is_not_falsely_converted():
    rows = trades()[:1]
    rows[0]["commissionAsset"] = "XYZ"
    report = build_historical_fee_observation(
        rows, [], expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert report.unpriced_commission_trade_count == 1
    assert report.weighted_fee_bps is None


def test_income_wrong_symbol_and_unknown_type_are_rejected():
    bad_symbol = income()[:1]
    bad_symbol[0]["symbol"] = "ETHUSDT"
    with pytest.raises(FeeObservationError, match="SYMBOL_MISMATCH"):
        build_historical_fee_observation(
            trades(), bad_symbol, expected_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
        )
    bad_type = income()[:1]
    bad_type[0]["incomeType"] = "FUNDING_FEE"
    with pytest.raises(FeeObservationError, match="INCOME_TYPE_INVALID"):
        build_historical_fee_observation(
            trades(), bad_type, expected_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
        )


def test_duplicate_trade_rows_are_not_silently_removed():
    rows = trades()[:1]
    report = build_historical_fee_observation(
        rows + rows, [], expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert report.trade_count == 2
    assert report.trade_commission_by_asset == (("USDT", "7.94", 2),)


def test_symbol_less_commission_income_is_not_attributed_to_a_trading_pair():
    row = income()[:1]
    row[0]["symbol"] = ""
    with pytest.raises(FeeObservationError, match="COMMISSION_SYMBOL_REQUIRED"):
        build_historical_fee_observation(
            trades(), row, expected_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
        )


def test_returned_snapshot_commission_totals_can_be_reconciled_without_claiming_coverage():
    trade_rows = trades()[:2]
    income_rows = income()[:2]
    report = build_historical_fee_observation(
        trade_rows, income_rows, expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert report.returned_snapshot_commission_reconciliation == "MATCHED_FOR_RETURNED_ROWS_ONLY"
    by_asset = {row[0]: row for row in report.commission_reconciliation_by_asset}
    assert by_asset["USDT"][2] == "-3.97"
    assert Decimal(by_asset["USDT"][3]) == Decimal("0")
    assert by_asset["BTC"][2] == "-0.00001"
    assert Decimal(by_asset["BTC"][3]) == Decimal("0")


def test_returned_snapshot_commission_mismatch_is_reported_not_hidden():
    trade_rows = trades()[:1]
    income_rows = income()[:1]
    income_rows[0]["income"] = "-3.00"
    report = build_historical_fee_observation(
        trade_rows, income_rows, expected_symbol="BTCUSDT",
        base_asset="BTC", quote_asset="USDT",
    )
    assert report.returned_snapshot_commission_reconciliation == "NOT_MATCHED_OR_COUNTERPART_MISSING"
    assert report.commission_reconciliation_by_asset[0][-1] == "MISMATCH"


@pytest.mark.parametrize("field,value,error", [
    ("incomeType", [], "INCOME_TYPE_INVALID"),
    ("incomeType", {"unknown": "type"}, "INCOME_TYPE_INVALID"),
    ("symbol", [], "SYMBOL_INVALID"),
])
def test_income_row_unhashable_or_wrong_type_fields_fail_closed(field, value, error):
    rows = income()[:1]
    rows[0][field] = value
    with pytest.raises(FeeObservationError, match=error):
        build_historical_fee_observation(
            trades(), rows, expected_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
        )
