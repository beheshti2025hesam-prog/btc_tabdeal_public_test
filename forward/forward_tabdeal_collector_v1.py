"""Branch-safe Tabdeal observation collector.

Fresh-data only. No Git commands, no pushes, no historical imports, no orders.
Sequence is informational metadata only; every trade payload is appended.
The collector remains disabled by default and is not the HES production data source.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websocket


WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
DEFAULT_OUTPUT = "data/forward/observations.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_trade(
    payload: dict[str, Any],
    *,
    raw_message: str | None = None,
    received_at: str | None = None,
) -> dict[str, Any] | None:
    """Preserve each trade payload; never require, coerce, compare, or deduplicate sequence."""
    event_type = str(payload.get("type", payload.get("event", ""))).lower()
    if "order" in event_type:
        return None

    data = payload.get("trade")
    if data is None:
        data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("symbol") or data.get("s") or SYMBOL
    if symbol != SYMBOL:
        return None

    received = received_at or _now()
    raw_json = raw_message if raw_message is not None else json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    source_updated = data.get("updated")
    raw_price = data.get("price", data.get("p"))
    raw_amount = data.get("amount", data.get("q"))
    price = None
    amount = None
    try:
        candidate = float(raw_price) if raw_price is not None else None
        if candidate is not None and math.isfinite(candidate) and candidate > 0:
            price = candidate
    except (TypeError, ValueError):
        pass
    try:
        candidate = float(raw_amount) if raw_amount is not None else None
        if candidate is not None and math.isfinite(candidate) and candidate > 0:
            amount = candidate
    except (TypeError, ValueError):
        pass

    return {
        "received_at": received,
        "observed_at": received,
        "source_updated": str(source_updated) if source_updated is not None else None,
        "event_timestamp": str(source_updated) if source_updated is not None else None,
        "market": symbol,
        "symbol": symbol,
        "price": price,
        "price_raw": raw_price,
        "amount": amount,
        "amount_raw": raw_amount,
        "side": str(data.get("side") or data.get("side_name") or data.get("S") or "UNKNOWN"),
        "sequence": data.get("sequence"),
        "raw_payload": payload,
        "raw_payload_json": raw_json,
        "raw_payload_sha256": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
        "source": "tabdeal_ws_forward_v1",
    }


class ForwardTabdealCollectorV1:
    def __init__(self, output: str = DEFAULT_OUTPUT, *, enabled: bool = False) -> None:
        self.output = Path(output)
        self.enabled = enabled

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run(self, *, run_seconds: int = 0) -> None:
        if not self.enabled:
            raise RuntimeError("Forward Tabdeal collector is disabled by default.")

        started = time.monotonic()
        while run_seconds == 0 or time.monotonic() - started < run_seconds:
            ws = None
            try:
                ws = websocket.create_connection(WS_URL, timeout=15)
                ws.send(SYMBOL)
                while run_seconds == 0 or time.monotonic() - started < run_seconds:
                    raw_message = ws.recv()
                    received_at = _now()
                    if not raw_message:
                        break
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    record = normalize_trade(
                        payload, raw_message=raw_message, received_at=received_at
                    )
                    if record is not None:
                        self._append(record)
            except Exception:
                # Reconnect/resubscribe only; no sequence-based resume or replay claim.
                pass
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
            if run_seconds and time.monotonic() - started >= run_seconds:
                break
            time.sleep(2)
