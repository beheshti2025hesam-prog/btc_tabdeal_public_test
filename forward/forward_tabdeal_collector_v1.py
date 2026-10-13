"""Branch-safe Tabdeal observation collector.

Fresh-data only. No Git commands, no pushes, no historical imports, no orders.
Opaque exchange sequence fields are preserved as evidence, never treated as
monotonic counters until their semantics are documented and pinned.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websocket


LOG = logging.getLogger(__name__)
WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
DEFAULT_OUTPUT = "data/forward/observations.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON numeric constant: {value}")


def normalize_trade(
    payload: dict[str, Any], *, raw_message: str | None = None
) -> dict[str, Any] | None:
    """Normalize a trade-shaped payload without assuming sequence semantics.

    The original WebSocket text and its exact SHA-256 are retained when the
    caller supplies them. The source sequence is opaque metadata: it is neither
    converted to an integer nor used as a deduplication/order key.
    """
    if not isinstance(payload, dict):
        return None

    event_type = str(payload.get("type", payload.get("event", ""))).lower()
    if "order" in event_type:
        return None

    data = payload.get("trade")
    if data is None:
        data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("symbol", data.get("s"))
    price_raw = data.get("price", data.get("p"))
    amount_raw = data.get("amount", data.get("q"))
    if "sequence" in data:
        source_sequence = data["sequence"]
    else:
        source_sequence = data.get("seq")
    side = data.get("side", data.get("side_name", data.get("S")))
    source_updated = data.get("updated")

    if symbol != SYMBOL or price_raw is None or amount_raw is None:
        return None
    if source_updated is None or not str(source_updated).strip():
        return None

    try:
        price = float(price_raw)
        amount = float(amount_raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(price) or not math.isfinite(amount):
        return None
    if price <= 0 or amount <= 0:
        return None

    record: dict[str, Any] = {
        "observed_at": _now(),
        "source_updated": str(source_updated),
        "symbol": SYMBOL,
        "price": price,
        "amount": amount,
        "side": str(side) if side is not None else "UNKNOWN",
        "sequence": source_sequence,
        "sequence_semantics": "UNKNOWN_OPAQUE",
        "source": "tabdeal_ws_forward_v1",
    }
    if raw_message is not None:
        record["raw_payload"] = raw_message
        record["raw_payload_sha256"] = hashlib.sha256(
            raw_message.encode("utf-8")
        ).hexdigest()
    return record


class ForwardTabdealCollectorV1:
    def __init__(self, output: str = DEFAULT_OUTPUT, *, enabled: bool = False) -> None:
        self.output = Path(output)
        self.enabled = enabled

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(record, sort_keys=True, allow_nan=False)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run(self, *, run_seconds: int = 0) -> None:
        if not self.enabled:
            raise RuntimeError("Forward Tabdeal collector is disabled by default.")
        if run_seconds < 0:
            raise ValueError("run_seconds must be non-negative")

        started = time.monotonic()

        while run_seconds == 0 or time.monotonic() - started < run_seconds:
            ws = None
            try:
                ws = websocket.create_connection(WS_URL, timeout=15)
                ws.send(SYMBOL)

                while run_seconds == 0 or time.monotonic() - started < run_seconds:
                    message = ws.recv()
                    if not message:
                        break

                    try:
                        payload = json.loads(
                            message, parse_constant=_reject_nonstandard_constant
                        )
                    except (json.JSONDecodeError, TypeError, ValueError):
                        LOG.warning("Ignoring malformed/non-standard JSON message")
                        continue

                    record = normalize_trade(payload, raw_message=message)
                    if record is None:
                        continue

                    # Preserve every valid trade-shaped observation. Sequence
                    # values are not a proven monotonic stream counter here.
                    self._append(record)
            except Exception:
                # Never hide a capture failure: log its traceback before
                # reconnecting, without fabricating observations or touching
                # persisted records.
                LOG.exception("Forward Tabdeal observation connection failed")
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        LOG.exception("Forward Tabdeal WebSocket close failed")

            if run_seconds and time.monotonic() - started >= run_seconds:
                break
            time.sleep(2)
