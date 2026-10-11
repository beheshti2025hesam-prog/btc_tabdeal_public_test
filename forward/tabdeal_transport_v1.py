"""Minimal read-only Tabdeal WebSocket transport boundary.

The transport owns bounded socket lifecycle and frame handoff. Optional raw
journaling preserves every frame and rejection before downstream handoff. It
never writes market data, commits Git, starts services, evaluates strategy, or
executes trades.
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
        raw_ingress_journal: Any | None = None,
        connection_generation: int = 1,
    ):
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if type(connection_generation) is not int or connection_generation < 0:
            raise ValueError("connection_generation must be a non-negative integer")
        self.as_of_provider = as_of_provider
        self.on_record = on_record
        self.on_frame_metadata = on_frame_metadata
        self.raw_ingress_journal = raw_ingress_journal
        self.connection_generation = connection_generation
        self.ws_factory = ws_factory
        self.url = url
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.frames_seen = 0
        self.records_emitted = 0
        self.rejected = 0
        self.ignored = 0
        self.rejection_reasons: list[str] = []
        self.closed_by_budget = False

    @staticmethod
    def _raw_bytes(message: Any) -> bytes:
        if isinstance(message, bytes):
            return message
        if isinstance(message, str):
            return message.encode("utf-8", errors="surrogatepass")
        raise TypeError("websocket message must be str or bytes")

    def _journal(
        self, *, event_type: str, received_at: str, monotonic_ns: int,
        verdict: str, raw_bytes: bytes | None = None,
        reason_code: str | None = None, details: dict[str, Any] | None = None,
    ) -> None:
        if self.raw_ingress_journal is None:
            return
        # Deliberately let journal failures propagate: do not pass unjournaled
        # frames to downstream consumers when audit persistence was requested.
        self.raw_ingress_journal.append(
            event_type=event_type,
            received_at_utc=received_at,
            receive_monotonic_ns=monotonic_ns,
            connection_generation=self.connection_generation,
            verdict=verdict,
            reason_code=reason_code,
            raw_bytes=raw_bytes,
            details=details or {},
        )

    def _open(self, ws: Any) -> None:
        ws.send(SYMBOL)
        self._journal(
            event_type="CONNECTED",
            received_at=datetime.now(timezone.utc).isoformat(),
            monotonic_ns=time.monotonic_ns(),
            verdict="ACCEPTED",
            details={"subscription": SYMBOL},
        )

    def _close(self, ws: Any, close_status_code: Any = None, close_msg: Any = None) -> None:
        details = {
            "close_status_code": close_status_code if type(close_status_code) is int else None,
            "close_message_present": bool(close_msg),
        }
        self._journal(
            event_type="DISCONNECT",
            received_at=datetime.now(timezone.utc).isoformat(),
            monotonic_ns=time.monotonic_ns(),
            verdict="DISCONNECTED",
            reason_code="SOCKET_CLOSED",
            details=details,
        )

    def _error(self, ws: Any, error: Any) -> None:
        self._journal(
            event_type="CONNECTION_ERROR",
            received_at=datetime.now(timezone.utc).isoformat(),
            monotonic_ns=time.monotonic_ns(),
            verdict="CONNECTION_ERROR",
            reason_code="WEBSOCKET_ERROR",
            details={"error_type": type(error).__name__},
        )

    def _message(self, ws: Any, message: str | bytes) -> None:
        self.frames_seen += 1
        received_at = datetime.now(timezone.utc).isoformat()
        received_monotonic_ns = time.monotonic_ns()
        raw_bytes = self._raw_bytes(message)
        raw_frame_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            payload = json.loads(message)
            trade = payload.get("trade") if isinstance(payload, dict) else None
            if not isinstance(trade, dict):
                self.ignored += 1
                self._journal(
                    event_type="FRAME", received_at=received_at,
                    monotonic_ns=received_monotonic_ns, verdict="IGNORED",
                    raw_bytes=raw_bytes, reason_code="UNSUPPORTED_ENVELOPE",
                    details={"raw_frame_sha256": raw_frame_sha256},
                )
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
            sequence_value = trade.get("sequence")
            safe_sequence_value = (
                sequence_value if type(sequence_value) is int
                or (type(sequence_value) is str and len(sequence_value) <= 64)
                else None
            )
            metadata = {
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
                "sequence_semantics": "OPAQUE_UNVERIFIED",
            }
            self._journal(
                event_type="FRAME", received_at=received_at,
                monotonic_ns=received_monotonic_ns, verdict="ACCEPTED",
                raw_bytes=raw_bytes, details=metadata,
            )
            if self.on_frame_metadata is not None:
                self.on_frame_metadata(metadata)
            self.on_record(record)
            self.records_emitted += 1
        except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            self.rejected += 1
            reason = type(exc).__name__
            self.rejection_reasons.append(reason)
            self._journal(
                event_type="FRAME", received_at=received_at,
                monotonic_ns=received_monotonic_ns, verdict="REJECTED",
                raw_bytes=raw_bytes, reason_code=reason,
                details={"raw_frame_sha256": raw_frame_sha256},
            )

    def _close_for_budget(self, ws: Any) -> None:
        self.closed_by_budget = True
        close = getattr(ws, "close", None)
        if callable(close):
            close()

    def run_once(self) -> None:
        ws = self.ws_factory(
            self.url, on_open=self._open, on_message=self._message,
            on_close=self._close, on_error=self._error,
        )
        timer = threading.Timer(
            self.max_runtime_seconds, self._close_for_budget, args=(ws,)
        )
        timer.daemon = True
        timer.start()
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        finally:
            timer.cancel()
