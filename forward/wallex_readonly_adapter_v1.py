"""Read-only Wallex Spot Socket.IO collector.

Wallex documents Socket.IO (v2-compatible client) and the Broadcaster event.
This adapter uses the Python Socket.IO v4 client, preserves unknown trade
sequence semantics, and performs no account or order operations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

SOCKETIO_URL = "https://api.wallex.ir"
SYMBOL = "BTCUSDT"
SOURCE = "wallex_spot_socketio_v1"


def _valid_symbol(symbol: str) -> bool:
    return isinstance(symbol, str) and bool(re.fullmatch(r"[A-Z0-9]{3,24}", symbol))


def _utc(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_trade(
    channel: str,
    data: dict[str, Any],
    *,
    symbol: str = SYMBOL,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate one documented Wallex Broadcaster trade event."""
    if not _valid_symbol(symbol):
        raise ValueError("invalid configured symbol")
    if channel != f"{symbol}@trade":
        raise ValueError("unexpected channel")
    if not isinstance(data, dict):
        raise ValueError("trade payload must be an object")
    price, quantity = data.get("price"), data.get("quantity")
    timestamp, is_buy = data.get("timestamp"), data.get("isBuyOrder")
    if price is None or quantity is None or timestamp is None or type(is_buy) is not bool:
        raise ValueError("missing or invalid documented trade fields")
    try:
        p, q = Decimal(str(price)), Decimal(str(quantity))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not p.is_finite() or not q.is_finite() or p <= 0 or q <= 0:
        raise ValueError("price and quantity must be finite and positive")
    source_updated = _utc(timestamp)
    received = received_at or datetime.now(timezone.utc)
    if received.tzinfo is None or received.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")
    canonical = json.dumps(
        {"channel": channel, "data": data},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return {
        "schema": "hes_normalized_trade_observation_v1",
        "source": SOURCE,
        "venue": "wallex",
        "product": "spot",
        "symbol": symbol,
        "price": str(p),
        "amount": str(q),
        "side": "BUY" if is_buy else "SELL",
        "source_updated": source_updated,
        "observed_at": received.astimezone(timezone.utc).isoformat(),
        "identity": {"kind": "raw_payload_sha256", "value": fingerprint},
        "sequence": None,
        "sequence_semantics": "NOT_DOCUMENTED_BY_VENUE",
        "raw_payload_sha256": fingerprint,
    }


class WallexReadOnlyCollectorV1:
    """Bounded Socket.IO collector. It persists observations only."""

    def __init__(
        self,
        output: str = "data/forward/wallex_btcusdt_observations.jsonl",
        *,
        symbol: str = SYMBOL,
        enabled: bool = False,
        max_runtime_seconds: float = 60.0,
        sio_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not _valid_symbol(symbol):
            raise ValueError("symbol must be an uppercase Wallex market symbol")
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.output = Path(output)
        self.symbol = symbol
        self.channel = f"{symbol}@trade"
        self.enabled = enabled
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.sio_factory = sio_factory
        self.frames_seen = 0
        self.records_written = 0
        self.rejected = 0
        self.ignored = 0
        self.last_error: str | None = None

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.records_written += 1

    def _handle_event(self, channel: str, data: Any) -> None:
        self.frames_seen += 1
        try:
            if channel != self.channel:
                self.ignored += 1
                return
            self._append(normalize_trade(channel, data, symbol=self.symbol))
        except (ValueError, TypeError, KeyError) as exc:
            self.rejected += 1
            self.last_error = type(exc).__name__

    def run_once(self) -> None:
        if not self.enabled:
            raise RuntimeError("Wallex collector is disabled by default")
        if self.sio_factory is None:
            import socketio
            sio = socketio.Client(reconnection=False, logger=False, engineio_logger=False)
        else:
            sio = self.sio_factory()

        @sio.on("connect")
        def _on_connect() -> None:
            sio.emit("subscribe", {"channel": self.channel})

        @sio.on("Broadcaster")
        def _on_broadcaster(channel: str, data: Any) -> None:
            self._handle_event(channel, data)

        @sio.on("connect_error")
        def _on_connect_error(_data: Any = None) -> None:
            self.last_error = "connect_error"

        deadline = time.monotonic() + self.max_runtime_seconds
        try:
            # Wallex's official examples use Socket.IO v2-compatible clients,
            # emitting "subscribe" and receiving the "Broadcaster" event.
            sio.connect(SOCKETIO_URL, transports=["websocket"])
            while time.monotonic() < deadline and getattr(sio, "connected", True):
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        except Exception as exc:
            self.last_error = type(exc).__name__
        finally:
            try:
                if getattr(sio, "connected", False):
                    sio.disconnect()
            except Exception:
                pass
