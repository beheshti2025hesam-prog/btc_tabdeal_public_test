"""Read-only Tabdeal WebSocket frame adapter.

This module parses already-received frames only. It does not open sockets,
persist data, start services, or execute trades. Network transport remains an
external boundary so this adapter is independently testable and fail-closed.

Tabdeal broadcast sequence semantics are undocumented. Preserve the raw value
as opaque metadata; never coerce it into an ordered/unique integer here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

SOURCE = "tabdeal_ws_forward_v1"
SYMBOL = "BTC_USDT"


def _timestamp(value: Any) -> str:
    if isinstance(value, (int, float)):
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


def parse_trade_frame(
    frame: dict[str, Any],
    *,
    as_of: datetime,
    raw_payload: str | bytes | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Parse a frame while retaining explicit provenance when supplied.

    session_id/run_id are passed through, never fabricated per frame. Callers
    that own the session/run lifecycle must create them once and pass them here.
    """
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
    if any(value is None for value in (price, amount, side, ts)):
        raise ValueError("incomplete trade frame")

    updated = _timestamp(ts)
    if datetime.fromisoformat(updated) > as_of.astimezone(timezone.utc):
        raise ValueError("future source observation")
    if Decimal(str(price)) <= 0 or Decimal(str(amount)) <= 0:
        raise ValueError("price and amount must be positive")
    if str(side).lower() not in {"buy", "sell", "b", "s"}:
        raise ValueError("unsupported side")

    record: dict[str, Any] = {
        "source": SOURCE,
        "symbol": SYMBOL,
        "price": str(price),
        "amount": str(amount),
        "side": str(side),
        "source_updated": updated,
        "sequence": sequence,
        "sequence_semantics": "UNKNOWN_OPAQUE",
    }
    for key, value in (("session_id", session_id), ("run_id", run_id)):
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string when supplied")
            record[key] = value

    if raw_payload is not None:
        raw_bytes = raw_payload if isinstance(raw_payload, bytes) else raw_payload.encode("utf-8")
        record["raw_payload_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        record["raw_payload"] = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload
    return record
