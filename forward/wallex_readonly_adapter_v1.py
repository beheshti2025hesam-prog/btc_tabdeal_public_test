"""Read-only Wallex Spot raw-WebSocket trade collector.

Wallex's official example opens wss://api.wallex.ir/ws and immediately sends
["subscribe", {"channel": "SYMBOL@trade"}]. This module follows that documented
raw-WebSocket protocol; it does not use Socket.IO or account/order APIs.
Trade IDs/sequences are not present in the observed payload. The canonical event
fingerprint is not a raw-byte hash and cannot prove completeness or deduplicate
equal trades. The collector separately records the exact received frame hash.
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

WEBSOCKET_URL = "wss://api.wallex.ir/ws"
SYMBOL = "BTCUSDT"
SOURCE = "wallex_spot_raw_websocket_v1"


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
    raw_frame_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate one documented Wallex trade event without inventing identity."""
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
        "identity": {"kind": "canonical_event_sha256", "value": fingerprint},
        "sequence": None,
        "sequence_semantics": "NOT_DOCUMENTED_BY_VENUE",
        "canonical_event_sha256": fingerprint,
        **({"raw_frame_sha256": raw_frame_sha256} if raw_frame_sha256 is not None else {}),
    }


class WallexReadOnlyCollectorV1:
    """Bounded raw-WebSocket collector; silent feeds fail closed."""

    def __init__(
        self,
        output: str = "data/forward/wallex_btcusdt_observations.jsonl",
        *,
        symbol: str = SYMBOL,
        enabled: bool = False,
        max_runtime_seconds: float = 60.0,
        ws_factory: Callable[[], Any] | None = None,
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

    def _record_event(
        self, channel: str, data: Any, *, raw_frame_sha256: str | None = None
    ) -> None:
        try:
            if channel != self.channel:
                self.ignored += 1
                return
            self._append(normalize_trade(
                channel, data, symbol=self.symbol, raw_frame_sha256=raw_frame_sha256
            ))
        except (ValueError, TypeError, KeyError) as exc:
            self.rejected += 1
            self.last_error = type(exc).__name__

    def _handle_event(self, channel: str, data: Any) -> None:
        """Test seam for one already-decoded event."""
        self.frames_seen += 1
        self._record_event(channel, data)

    def _consume_frame(self, frame: Any) -> None:
        self.frames_seen += 1
        if isinstance(frame, bytes):
            raw = frame.decode("utf-8", "strict")
        elif isinstance(frame, str):
            raw = frame
        else:
            self.rejected += 1
            self.last_error = "invalid_frame_type"
            return
        raw_frame = frame if isinstance(frame, bytes) else raw.encode("utf-8")
        raw_frame_sha256 = hashlib.sha256(raw_frame).hexdigest()
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.rejected += 1
            self.last_error = "malformed_json"
            return
        if not isinstance(payload, list) or len(payload) != 2:
            self.ignored += 1
            return
        channel, data = payload
        if not isinstance(channel, str):
            self.rejected += 1
            self.last_error = "invalid_channel"
            return
        self._record_event(channel, data, raw_frame_sha256=raw_frame_sha256)

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        return isinstance(exc, TimeoutError) or type(exc).__name__ in {
            "WebSocketTimeoutException", "timeout",
        }

    def run_once(self) -> None:
        if not self.enabled:
            raise RuntimeError("Wallex collector is disabled by default")
        records_before = self.records_written
        try:
            if self.ws_factory is None:
                import websocket

                ws = websocket.create_connection(
                    WEBSOCKET_URL,
                    timeout=min(5.0, self.max_runtime_seconds),
                    http_proxy_host=None,
                    http_no_proxy=["*"],
                )
            else:
                ws = self.ws_factory()
        except Exception as exc:
            self.last_error = type(exc).__name__
            raise RuntimeError("Wallex WebSocket connection failed; refusing success-shaped return") from exc

        deadline = time.monotonic() + self.max_runtime_seconds
        try:
            try:
                # Per Wallex's official example, send on socket open.
                ws.send(json.dumps(["subscribe", {"channel": self.channel}], separators=(",", ":")))
            except Exception as exc:
                self.last_error = type(exc).__name__
                raise RuntimeError("Wallex WebSocket subscription failed; refusing success-shaped return") from exc
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if hasattr(ws, "settimeout"):
                    ws.settimeout(min(1.0, max(0.05, remaining)))
                try:
                    frame = ws.recv()
                except Exception as exc:
                    if self._is_timeout(exc):
                        time.sleep(min(0.02, max(0.0, remaining)))
                        continue
                    self.last_error = type(exc).__name__
                    raise RuntimeError("Wallex WebSocket disconnected during bounded collection") from exc
                if frame is None:
                    self.last_error = "connection_closed"
                    raise RuntimeError("Wallex WebSocket closed during bounded collection")
                self._consume_frame(frame)

            if self.records_written == records_before:
                self.last_error = "no_trade_events_received"
                raise RuntimeError("Wallex WebSocket produced no valid trade events; refusing success-shaped return")
        finally:
            try:
                ws.close()
            except Exception:
                pass
