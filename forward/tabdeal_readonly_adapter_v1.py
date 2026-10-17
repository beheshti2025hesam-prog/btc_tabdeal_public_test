"""Read-only Tabdeal WebSocket frame adapter.

This module parses already-received frames only. It does not open sockets,
persist data, start services, or execute trades. Network transport remains an
external boundary so this adapter is independently testable and fail-closed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

SOURCE = "tabdeal_ws_forward_v1"
SYMBOL = "BTC_USDT"


def _timestamp(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("invalid timestamp")
    if isinstance(value, (int, float)):
        # Tabdeal-style millisecond timestamps are normalized to UTC ISO.
        value = float(value)
        if value > 1e11:
            value /= 1000
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        dt = dt.astimezone(timezone.utc)
    else:
        raise ValueError("invalid timestamp")
    return dt.isoformat()


def parse_trade_frame(frame: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if frame.get("type") not in {"trade", "aggTrade", "match"}:
        raise ValueError("unsupported frame type")
    symbol = frame.get("symbol") or frame.get("s")
    if symbol != SYMBOL:
        raise ValueError("unsupported symbol")
    price = frame.get("price", frame.get("p"))
    amount = frame.get("amount", frame.get("q"))
    side = frame.get("side", frame.get("S"))
    sequence = frame.get("sequence", frame.get("seq", frame.get("id")))
    ts = frame.get("source_updated", frame.get("timestamp", frame.get("T", frame.get("time"))))
    if any(v is None for v in (price, amount, side, sequence, ts)):
        raise ValueError("incomplete trade frame")
    updated = _timestamp(ts)
    dt = datetime.fromisoformat(updated)
    if dt > as_of.astimezone(timezone.utc):
        raise ValueError("future source observation")
    if Decimal(str(price)) <= 0 or Decimal(str(amount)) <= 0:
        raise ValueError("price and amount must be positive")
    if str(side).lower() not in {"buy", "sell", "b", "s"}:
        raise ValueError("unsupported side")
    # bool is an int subclass, and floats can be silently truncated by int().
    # Preserve the wire type boundary before normalizing an opaque identifier.
    if type(sequence) not in (int, str):
        raise ValueError("invalid sequence")
    try:
        seq = int(sequence)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid sequence") from exc
    if seq < 0:
        raise ValueError("invalid sequence")
    record = {
        "source": SOURCE,
        "symbol": SYMBOL,
        "price": str(price),
        "amount": str(amount),
        "side": str(side),
        "source_updated": updated,
        "sequence": seq,
    }
    # The trusted transport computes this digest from its received callback
    # payload. Preserve it across normalization so the downstream sequence
    # observer can distinguish exact replay from a repeated opaque sequence.
    if "raw_payload_sha256" in frame:
        record["raw_payload_sha256"] = frame["raw_payload_sha256"]
    return record
