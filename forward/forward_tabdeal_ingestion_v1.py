"""Read-only adapter from Tabdeal forward trade records to candle input.

No network, persistence, strategy, or execution occurs here. This boundary
accepts only fresh, schema-valid observations and delegates aggregation to the
existing deterministic candle normalizer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from .candle_normalizer_v1 import TradeObservation, Candle15m, IntervalGap, normalize_trades

REQUIRED = ("symbol", "price", "amount", "side", "source_updated", "sequence")
SOURCE = "tabdeal_ws_forward_v1"


def _dt(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("source_updated must be an ISO timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid source_updated timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("source_updated must be timezone-aware")
    return dt.astimezone(timezone.utc)


def to_trade_observation(record: dict[str, Any], *, as_of: datetime) -> TradeObservation:
    missing = [key for key in REQUIRED if key not in record]
    if missing:
        raise ValueError("missing ingestion fields:" + ",".join(missing))
    if record.get("source") != SOURCE:
        raise ValueError("unsupported ingestion source")
    updated = _dt(record["source_updated"])
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    if updated > as_of:
        raise ValueError("future source observation")
    if record["symbol"] != "BTC_USDT":
        raise ValueError("unsupported symbol")
    sequence = record["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, (int, str)) or sequence == "":
        raise ValueError("invalid sequence type")
    return TradeObservation(
        symbol=record["symbol"],
        price=Decimal(str(record["price"])),
        amount=Decimal(str(record["amount"])),
        side=str(record["side"]),
        updated=updated,
        sequence=sequence,
    )


def ingest_closed_candles(
    records: Iterable[dict[str, Any]], *, as_of: datetime
) -> tuple[tuple[Candle15m, ...], tuple[IntervalGap, ...]]:
    trades = tuple(to_trade_observation(record, as_of=as_of) for record in records)
    return normalize_trades(trades, as_of=as_of, expected_symbol="BTC_USDT")
