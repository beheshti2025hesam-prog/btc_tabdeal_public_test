"""Read-only Wallex Spot WebSocket adapter.

Uses Wallex's documented raw WebSocket endpoint wss://api.wallex.ir/ws and
JSON subscribe frame ["subscribe", {"channel": "BTCUSDT@trade"}]. No API key,
account access, order placement, or Git side effects. The venue documents no
per-trade sequence ID; this adapter never fabricates one.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

WS_URL = "wss://api.wallex.ir/ws"
SYMBOL = "BTCUSDT"
CHANNEL = f"{SYMBOL}@trade"
SOURCE = "wallex_spot_websocket_v1"


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


def normalize_trade(channel: str, data: dict[str, Any], *, received_at: datetime | None = None) -> dict[str, Any]:
    """Validate one documented Wallex SYMBOL@trade WebSocket message."""
    if channel != CHANNEL:
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
        {"channel": channel, "data": data}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return {
        "schema": "hes_normalized_trade_observation_v1",
        "source": SOURCE,
        "venue": "wallex",
        "product": "spot",
        "symbol": SYMBOL,
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
    """Bounded WebSocket collector. It persists observations only; trading is impossible."""

    def __init__(
        self,
        output: str = "data/forward/wallex_btcusdt_observations.jsonl",
        *,
        enabled: bool = False,
        max_runtime_seconds: float = 60.0,
        ws_factory: Callable[..., Any] | None = None,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.output = Path(output)
        self.enabled = enabled
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.ws_factory = ws_factory
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

    def _handle_message(self, message: str) -> None:
        self.frames_seen += 1
        try:
            frame = json.loads(message)
            if not isinstance(frame, list) or len(frame) != 2:
                self.ignored += 1
                return
            channel, data = frame
            if channel != CHANNEL:
                self.ignored += 1
                return
            self._append(normalize_trade(channel, data))
        except (ValueError, TypeError, KeyError) as exc:
            self.rejected += 1
            self.last_error = type(exc).__name__

    def run_once(self) -> None:
        if not self.enabled:
            raise RuntimeError("Wallex collector is disabled by default")
        if self.ws_factory is None:
            import websocket
            factory = websocket.create_connection
        else:
            factory = self.ws_factory

        ws = factory(WS_URL, timeout=10)
        try:
            ws.send(json.dumps(["subscribe", {"channel": CHANNEL}]))
            ws.settimeout(1.0)
            deadline = time.monotonic() + self.max_runtime_seconds
            while time.monotonic() < deadline:
                try:
                    message = ws.recv()
                except Exception as exc:
                    # Socket timeout is a normal polling interval; other socket
                    # errors terminate this bounded attempt.
                    try:
                        import websocket
                        if isinstance(exc, websocket.WebSocketTimeoutException):
                            continue
                    except ImportError:
                        pass
                    self.last_error = type(exc).__name__
                    break
                if not message:
                    self.last_error = "empty_frame"
                    break
                self._handle_message(message)
        finally:
            try:
                ws.close()
            except Exception:
                pass
