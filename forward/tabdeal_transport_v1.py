"""Bounded, read-only Tabdeal WebSocket transport boundary.

The transport owns only socket lifecycle and frame handoff. It never writes
market data, commits Git, starts systemd, evaluates strategy, or executes.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable

from .tabdeal_readonly_adapter_v1 import parse_trade_frame

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"


class TabdealReadOnlyTransportV1:
    def __init__(
        self,
        *,
        as_of_provider: Callable[[], Any],
        on_record: Callable[[dict[str, Any]], None],
        ws_factory: Callable[..., Any],
        url: str = WS_URL,
        max_runtime_seconds: float = 60.0,
    ):
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.as_of_provider = as_of_provider
        self.on_record = on_record
        self.ws_factory = ws_factory
        self.url = url
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.frames_seen = 0
        self.records_emitted = 0
        self.ignored_non_trade = 0
        self.rejected = 0
        self.rejection_reasons: list[str] = []
        self.timed_out = False
        self.closed = False

    def _open(self, ws: Any) -> None:
        ws.send(SYMBOL)

    def _message(self, ws: Any, message: str) -> None:
        self.frames_seen += 1
        try:
            payload = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            self.rejected += 1
            self.rejection_reasons.append("INVALID_JSON")
            return

        trade = payload.get("trade") if isinstance(payload, dict) else None
        if not isinstance(trade, dict):
            self.ignored_non_trade += 1
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
        try:
            record = parse_trade_frame(frame, as_of=self.as_of_provider())
        except (ValueError, TypeError, KeyError) as exc:
            self.rejected += 1
            self.rejection_reasons.append(str(exc))
            return

        self.on_record(record)
        self.records_emitted += 1

    def _timeout_close(self, ws: Any) -> None:
        self.timed_out = True
        close = getattr(ws, "close", None)
        if callable(close):
            close()

    def run_once(self) -> None:
        ws = self.ws_factory(
            self.url,
            on_open=self._open,
            on_message=self._message,
        )
        timer = threading.Timer(self.max_runtime_seconds, self._timeout_close, args=(ws,))
        timer.daemon = True
        timer.start()
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        finally:
            timer.cancel()
            self.closed = True
            close = getattr(ws, "close", None)
            if callable(close):
                close()
