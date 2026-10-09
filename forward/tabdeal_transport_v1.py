"""Minimal read-only Tabdeal WebSocket transport boundary.

The transport owns only bounded socket lifecycle and frame handoff. It never
writes market data, commits Git, starts systemd, evaluates strategy, or executes.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .tabdeal_readonly_adapter_v1 import parse_trade_frame

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"


class TabdealReadOnlyTransportV1:
    def __init__(
        self, *, as_of_provider: Callable[[], Any],
        on_record: Callable[[dict[str, Any]], None],
        ws_factory: Callable[..., Any], url: str = WS_URL,
        max_runtime_seconds: float = 60.0,
        on_frame_metadata: Callable[[dict[str, Any]], None] | None = None,
    ):
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.as_of_provider = as_of_provider
        self.on_record = on_record
        self.on_frame_metadata = on_frame_metadata
        self.ws_factory = ws_factory
        self.url = url
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.frames_seen = 0
        self.records_emitted = 0
        self.rejected = 0
        self.ignored = 0
        self.rejection_reasons: list[str] = []
        self.closed_by_budget = False

    def _open(self, ws: Any) -> None:
        ws.send(SYMBOL)

    def _message(self, ws: Any, message: str) -> None:
        self.frames_seen += 1
        received_at = datetime.now(timezone.utc).isoformat()
        received_monotonic_ns = time.monotonic_ns()
        raw_bytes = message.encode("utf-8", errors="replace") if isinstance(message, str) else bytes(message)
        raw_frame_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            payload = json.loads(message)
            trade = payload.get("trade") if isinstance(payload, dict) else None
            if not isinstance(trade, dict):
                self.ignored += 1
                return
            frame = {
                "type": "trade",
                "symbol": trade.get("symbol", SYMBOL),
                "price": trade.get("price"),
                "amount": trade.get("amount"),
                "side": trade.get("side", trade.get("side_name")),
                "sequence": trade.get("sequence"),
                "timestamp": trade.get("updated"),
            }
            record = parse_trade_frame(frame, as_of=self.as_of_provider())
            if self.on_frame_metadata is not None:
                sequence_value = trade.get("sequence")
                safe_sequence_value = (
                    sequence_value if type(sequence_value) is int
                    or (type(sequence_value) is str and len(sequence_value) <= 64)
                    else None
                )
                self.on_frame_metadata({
                    "schema": "hes_transport_frame_fingerprint_v1",
                    "raw_frame_sha256": raw_frame_sha256,
                    "received_at_utc": received_at,
                    "receive_monotonic_ns": received_monotonic_ns,
                    "outer_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
                    "trade_keys": sorted(trade.keys()),
                    "sequence_field_path": "trade.sequence" if "sequence" in trade else None,
                    "sequence_value_type": type(sequence_value).__name__,
                    "sequence_value": safe_sequence_value,
                    "normalized_sequence": record.get("sequence"),
                })
            self.on_record(record)
            self.records_emitted += 1
        except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            self.rejected += 1
            self.rejection_reasons.append(type(exc).__name__)

    def _close_for_budget(self, ws: Any) -> None:
        self.closed_by_budget = True
        close = getattr(ws, "close", None)
        if callable(close):
            close()

    def run_once(self) -> None:
        ws = self.ws_factory(self.url, on_open=self._open, on_message=self._message)
        timer = threading.Timer(
            self.max_runtime_seconds, self._close_for_budget, args=(ws,)
        )
        timer.daemon = True
        timer.start()
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        finally:
            timer.cancel()
