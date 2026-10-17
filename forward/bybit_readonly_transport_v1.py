"""Bounded, read-only Bybit V5 public market-data transport.

This adapter captures public linear-market trade/kline frames only. It does not
authenticate, access private account data, submit orders, or interpret sequence
semantics. Keep the raw-frame fingerprint as evidence; downstream acceptance
requires the HES source/sequence gates to pass independently.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

WS_URL = "wss://stream.bybit.com/v5/public/linear"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "1"


class BybitReadOnlyTransportV1:
    def __init__(
        self,
        *,
        on_frame: Callable[[dict[str, Any]], None],
        ws_factory: Callable[..., Any],
        symbol: str = DEFAULT_SYMBOL,
        interval: str = DEFAULT_INTERVAL,
        url: str = WS_URL,
        max_runtime_seconds: float = 60.0,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if not symbol or symbol != symbol.upper() or not symbol.isalnum():
            raise ValueError("symbol must be an uppercase alphanumeric exchange symbol")
        if interval not in {"1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"}:
            raise ValueError("unsupported Bybit kline interval")
        if not url.startswith("wss://stream.bybit.com/v5/public/linear"):
            raise ValueError("only the official Bybit public linear WebSocket endpoint is allowed")
        self.on_frame = on_frame
        self.ws_factory = ws_factory
        self.symbol = symbol
        self.interval = interval
        self.url = url
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.frames_seen = 0
        self.frames_emitted = 0
        self.ignored = 0
        self.rejected = 0
        self.closed_by_budget = False

    def _open(self, ws: Any) -> None:
        ws.send(json.dumps({
            "op": "subscribe",
            "args": [f"publicTrade.{self.symbol}", f"kline.{self.interval}.{self.symbol}"],
        }, separators=(",", ":")))

    def _message(self, ws: Any, message: Any) -> None:
        self.frames_seen += 1
        raw = message.encode("utf-8") if isinstance(message, str) else bytes(message)
        received_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                self.ignored += 1
                return
            topic = payload.get("topic")
            if not isinstance(topic, str):
                # Keep control/heartbeat messages out of the market-data journal.
                self.ignored += 1
                return
            expected = {f"publicTrade.{self.symbol}", f"kline.{self.interval}.{self.symbol}"}
            if topic not in expected:
                self.rejected += 1
                return
            data = payload.get("data")
            if not isinstance(data, list) or not data or not all(isinstance(x, dict) for x in data):
                self.rejected += 1
                return
            self.on_frame({
                "schema": "hes_bybit_public_frame_fingerprint_v1",
                "venue": "bybit",
                "market": "linear",
                "symbol": self.symbol,
                "topic": topic,
                "received_at_utc": received_at,
                "receive_monotonic_ns": time.monotonic_ns(),
                "raw_frame_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            })
            self.frames_emitted += 1
        except (ValueError, TypeError, json.JSONDecodeError):
            self.rejected += 1

    def _close_for_budget(self, ws: Any) -> None:
        self.closed_by_budget = True
        close = getattr(ws, "close", None)
        if callable(close):
            close()

    def run_once(self) -> None:
        ws = self.ws_factory(self.url, on_open=self._open, on_message=self._message)
        timer = threading.Timer(self.max_runtime_seconds, self._close_for_budget, args=(ws,))
        timer.daemon = True
        timer.start()
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        finally:
            timer.cancel()
