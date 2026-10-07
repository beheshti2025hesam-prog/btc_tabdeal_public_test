"""Branch-safe Tabdeal observation collector.

Fresh-data only. No Git commands, no pushes, no historical imports, no orders.
"""

from __future__ import annotations

import json
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


def _sequence(value: Any) -> int:
    return int(value)


def normalize_trade(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize only a trade-shaped payload; order events are rejected."""
    event_type = str(payload.get("type", payload.get("event", ""))).lower()
    if "order" in event_type:
        return None

    data = payload.get("trade")
    if data is None:
        data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("symbol") or data.get("s")
    price = data.get("price") or data.get("p")
    amount = data.get("amount") or data.get("q")
    sequence = data.get("sequence") or data.get("seq")
    side = data.get("side") or data.get("side_name") or data.get("S")
    source_updated = data.get("updated")

    if symbol != SYMBOL or price is None or amount is None or sequence is None:
        return None
    if source_updated is None:
        return None

    return {
        "observed_at": _now(),
        "source_updated": str(source_updated),
        "symbol": SYMBOL,
        "price": float(price),
        "amount": float(amount),
        "side": str(side) if side is not None else "UNKNOWN",
        "sequence": _sequence(sequence),
        "source": "tabdeal_ws_forward_v1",
    }


class ForwardTabdealCollectorV1:
    def __init__(self, output: str = DEFAULT_OUTPUT, *, enabled: bool = False) -> None:
        self.output = Path(output)
        self.enabled = enabled
        self.last_sequence: int | None = None

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run(self, *, run_seconds: int = 0) -> None:
        if not self.enabled:
            raise RuntimeError("Forward Tabdeal collector is disabled by default.")

        started = time.monotonic()

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return

            record = normalize_trade(payload)
            if record is None:
                return

            seq = record["sequence"]
            if self.last_sequence is not None and seq <= self.last_sequence:
                return

            self._append(record)
            self.last_sequence = seq

        ws = websocket.WebSocketApp(
            WS_URL,
            on_message=on_message,
        )

        # The process wrapper owns the finite/continuous lifetime.
        while run_seconds == 0 or time.monotonic() - started < run_seconds:
            ws.run_forever()
            if run_seconds and time.monotonic() - started >= run_seconds:
                break
            time.sleep(5)
