"""Offline, historical-only Tabdeal Futures fee observation parser.

This module consumes already retrieved API payloads. It performs no network
requests, never changes simulator fee settings, and cannot verify future fee
tiers. Exact symbols are compared as supplied; no alias normalization occurs.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

D = Decimal
INCOME_TYPES = {
    "Transfer", "TakerCommission", "MakerCommission", "TradePNL",
    "AdlPNL", "Liquidation", "InsuranceFund",
}


class FeeObservationError(ValueError):
    """Malformed or out-of-scope historical fee evidence."""


@dataclass(frozen=True)
class TradeFeeObservation:
    symbol: str
    trade_id: int
    order_id: int
    time_ms: int
    maker: bool
    commission: str
    commission_asset: str
    quote_quantity: str
    price: str
    commission_quote_equivalent: str | None
    fee_bps_quote_equivalent: str | None


@dataclass(frozen=True)
class IncomeObservation:
    symbol: str
    income_type: str
    amount: str
    asset: str
    time_ms: int


@dataclass(frozen=True)
class FeeObservationReport:
    status: str
    venue: str
    requested_symbol: str
    quote_asset: str
    trade_count: int
    maker_trade_count: int
    taker_trade_count: int
    quote_comparable_trade_count: int
    unpriced_commission_trade_count: int
    total_quote_notional: str
    total_quote_equivalent_commission: str
    weighted_fee_bps: str | None
    maker_weighted_fee_bps: str | None
    taker_weighted_fee_bps: str | None
    trade_commission_by_asset: tuple[tuple[str, str, int], ...]
    income_by_type_and_asset: tuple[tuple[str, str, str, int], ...]
    commission_reconciliation_by_asset: tuple[tuple[str, str, str, str, str], ...]
    returned_snapshot_commission_reconciliation: str
    trades: tuple[TradeFeeObservation, ...]
    income_rows: tuple[IncomeObservation, ...]
    user_trades_response_sha256: str
    income_response_sha256: str
    income_trade_reconciliation: str
    fee_schedule_verified: bool = False
    future_fee_tier_verified: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise FeeObservationError(f"{field}_INVALID")
    try:
        result = D(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise FeeObservationError(f"{field}_INVALID") from None
    if not result.is_finite() or (positive and result <= 0):
        raise FeeObservationError(f"{field}_INVALID")
    return result


def _integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise FeeObservationError(f"{field}_INVALID")
    return value


def _payload(value: bytes | str | Sequence[Mapping[str, object]], field: str):
    if isinstance(value, bytes):
        raw = value
        try:
            rows = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FeeObservationError(f"{field}_INVALID_JSON") from None
    elif isinstance(value, str):
        raw = value.encode("utf-8")
        try:
            rows = json.loads(value)
        except json.JSONDecodeError:
            raise FeeObservationError(f"{field}_INVALID_JSON") from None
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = list(value)
        try:
            raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            raise FeeObservationError(f"{field}_NOT_JSON_SERIALIZABLE") from None
    else:
        raise FeeObservationError(f"{field}_TYPE_INVALID")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise FeeObservationError(f"{field}_SHAPE_INVALID")
    return rows, hashlib.sha256(raw).hexdigest()


def build_historical_fee_observation(
    user_trades_payload: bytes | str | Sequence[Mapping[str, object]],
    income_payload: bytes | str | Sequence[Mapping[str, object]],
    *,
    expected_symbol: str,
    base_asset: str,
    quote_asset: str,
) -> FeeObservationReport:
    """Summarize documented Tabdeal userTrades and income rows, without inference.

    Commission is converted to quote terms only when its asset is exactly the
    quote asset, or exactly the base asset (using the same fill's price).
    Third-asset commissions remain unpriced. Income rows have no documented
    stable row ID in the current Tabdeal example, so every row is preserved;
    no timestamp/hash-based deduplication is performed.
    """
    for value, field in (
        (expected_symbol, "EXPECTED_SYMBOL"),
        (base_asset, "BASE_ASSET"),
        (quote_asset, "QUOTE_ASSET"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise FeeObservationError(f"{field}_INVALID")
    if base_asset == quote_asset:
        raise FeeObservationError("BASE_AND_QUOTE_ASSET_MUST_DIFFER")

    trade_rows, trade_hash = _payload(user_trades_payload, "USER_TRADES")
    income_rows, income_hash = _payload(income_payload, "INCOME")

    trades: list[TradeFeeObservation] = []
    by_asset: dict[str, list[Decimal | int]] = defaultdict(lambda: [D("0"), 0])
    by_role: dict[str, list[Decimal]] = {
        "maker": [D("0"), D("0")],
        "taker": [D("0"), D("0")],
    }
    total_notional = D("0")
    total_quote_fee = D("0")
    comparable_count = 0
    unpriced_count = 0

    for index, row in enumerate(trade_rows):
        prefix = f"USER_TRADES_ROW_{index}"
        symbol = row.get("symbol")
        if symbol != expected_symbol:
            raise FeeObservationError(f"{prefix}_SYMBOL_MISMATCH")
        trade_id = _integer(row.get("id"), f"{prefix}_ID")
        order_id = _integer(row.get("orderId"), f"{prefix}_ORDER_ID")
        time_ms = _integer(row.get("time"), f"{prefix}_TIME")
        maker = row.get("maker")
        if type(maker) is not bool:
            raise FeeObservationError(f"{prefix}_MAKER_INVALID")
        price = _decimal(row.get("price"), f"{prefix}_PRICE", positive=True)
        quote_qty = _decimal(row.get("quoteQty"), f"{prefix}_QUOTE_QTY", positive=True)
        commission = _decimal(row.get("commission"), f"{prefix}_COMMISSION")
        if commission < 0:
            raise FeeObservationError(f"{prefix}_COMMISSION_NEGATIVE")
        asset = row.get("commissionAsset")
        if not isinstance(asset, str) or not asset.strip():
            raise FeeObservationError(f"{prefix}_COMMISSION_ASSET_INVALID")

        quote_equivalent = None
        fee_bps = None
        if asset == quote_asset:
            quote_equivalent = commission
        elif asset == base_asset:
            quote_equivalent = commission * price

        by_asset[asset][0] += commission
        by_asset[asset][1] += 1
        if quote_equivalent is None:
            unpriced_count += 1
        else:
            comparable_count += 1
            total_notional += quote_qty
            total_quote_fee += quote_equivalent
            role = "maker" if maker else "taker"
            by_role[role][0] += quote_equivalent
            by_role[role][1] += quote_qty
            fee_bps = quote_equivalent / quote_qty * D("10000")

        trades.append(TradeFeeObservation(
            symbol=symbol,
            trade_id=trade_id,
            order_id=order_id,
            time_ms=time_ms,
            maker=maker,
            commission=str(commission),
            commission_asset=asset,
            quote_quantity=str(quote_qty),
            price=str(price),
            commission_quote_equivalent=(
                None if quote_equivalent is None else str(quote_equivalent)
            ),
            fee_bps_quote_equivalent=None if fee_bps is None else str(fee_bps),
        ))

    income_observations: list[IncomeObservation] = []
    income_totals: dict[tuple[str, str], list[Decimal | int]] = defaultdict(
        lambda: [D("0"), 0]
    )
    for index, row in enumerate(income_rows):
        prefix = f"INCOME_ROW_{index}"
        symbol = row.get("symbol", "")
        if not isinstance(symbol, str):
            raise FeeObservationError(f"{prefix}_SYMBOL_INVALID")
        if symbol and symbol != expected_symbol:
            raise FeeObservationError(f"{prefix}_SYMBOL_MISMATCH")
        income_type = row.get("incomeType")
        if not isinstance(income_type, str) or income_type not in INCOME_TYPES:
            raise FeeObservationError(f"{prefix}_INCOME_TYPE_INVALID")
        if income_type in {"TakerCommission", "MakerCommission"} and symbol != expected_symbol:
            raise FeeObservationError(f"{prefix}_COMMISSION_SYMBOL_REQUIRED")
        amount = _decimal(row.get("income"), f"{prefix}_INCOME")
        asset = row.get("asset")
        if not isinstance(asset, str) or not asset.strip():
            raise FeeObservationError(f"{prefix}_ASSET_INVALID")
        time_ms = _integer(row.get("time"), f"{prefix}_TIME")
        income_observations.append(IncomeObservation(
            symbol=symbol,
            income_type=income_type,
            amount=str(amount),
            asset=asset,
            time_ms=time_ms,
        ))
        income_totals[(income_type, asset)][0] += amount
        income_totals[(income_type, asset)][1] += 1

    trade_commission_totals = {
        asset: D(values[0]) for asset, values in by_asset.items()
    }
    income_commission_totals: dict[str, Decimal] = defaultdict(lambda: D("0"))
    for (kind, asset), values in income_totals.items():
        if kind in {"TakerCommission", "MakerCommission"}:
            income_commission_totals[asset] += D(values[0])
    reconciliation_rows = []
    reconciliation_states = []
    for asset in sorted(set(trade_commission_totals) | set(income_commission_totals)):
        trade_amount = trade_commission_totals.get(asset)
        income_amount = income_commission_totals.get(asset)
        if trade_amount is None or income_amount is None:
            delta = None
            state = "MISSING_COUNTERPART_IN_RETURNED_ROWS"
        else:
            delta = abs(trade_amount - abs(income_amount))
            state = "MATCHED" if delta == 0 else "MISMATCH"
        reconciliation_states.append(state)
        reconciliation_rows.append((
            asset,
            "" if trade_amount is None else str(trade_amount),
            "" if income_amount is None else str(income_amount),
            "" if delta is None else str(delta),
            state,
        ))
    if not reconciliation_rows:
        reconciliation_status = "NO_COMMISSION_ROWS_TO_COMPARE"
    elif all(state == "MATCHED" for state in reconciliation_states):
        reconciliation_status = "MATCHED_FOR_RETURNED_ROWS_ONLY"
    else:
        reconciliation_status = "NOT_MATCHED_OR_COUNTERPART_MISSING"

    weighted = (
        None if total_notional == 0
        else str(total_quote_fee / total_notional * D("10000"))
    )
    maker_weighted = (
        None if by_role["maker"][1] == 0
        else str(by_role["maker"][0] / by_role["maker"][1] * D("10000"))
    )
    taker_weighted = (
        None if by_role["taker"][1] == 0
        else str(by_role["taker"][0] / by_role["taker"][1] * D("10000"))
    )

    return FeeObservationReport(
        status="HISTORICAL_OBSERVATION_ONLY",
        venue="tabdeal",
        requested_symbol=expected_symbol,
        quote_asset=quote_asset,
        trade_count=len(trades),
        maker_trade_count=sum(1 for row in trades if row.maker),
        taker_trade_count=sum(1 for row in trades if not row.maker),
        quote_comparable_trade_count=comparable_count,
        unpriced_commission_trade_count=unpriced_count,
        total_quote_notional=str(total_notional),
        total_quote_equivalent_commission=str(total_quote_fee),
        weighted_fee_bps=weighted,
        maker_weighted_fee_bps=maker_weighted,
        taker_weighted_fee_bps=taker_weighted,
        trade_commission_by_asset=tuple(
            (asset, str(values[0]), int(values[1]))
            for asset, values in sorted(by_asset.items())
        ),
        income_by_type_and_asset=tuple(
            (kind, asset, str(values[0]), int(values[1]))
            for (kind, asset), values in sorted(income_totals.items())
        ),
        commission_reconciliation_by_asset=tuple(reconciliation_rows),
        returned_snapshot_commission_reconciliation=reconciliation_status,
        trades=tuple(trades),
        income_rows=tuple(income_observations),
        user_trades_response_sha256=trade_hash,
        income_response_sha256=income_hash,
        income_trade_reconciliation=(
            "NOT_PERFORMED_WINDOW_ALIGNMENT_AND_COMPLETE_COVERAGE_UNVERIFIED"
        ),
    )
