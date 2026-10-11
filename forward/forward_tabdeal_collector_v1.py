"""Branch-safe Tabdeal observation collector.

Fresh-data only. No Git commands, no pushes, no historical imports, no orders.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websocket

from .raw_ingress_journal_v1 import RawIngressJournalV1


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
    def __init__(
        self, output: str = DEFAULT_OUTPUT, *, enabled: bool = False,
        raw_ingress_journal: RawIngressJournalV1 | None = None,
    ) -> None:
        self.output = Path(output)
        self.enabled = enabled
        self.last_sequence: int | None = None
        # Constructing the sidecar does not create files; writes begin only when
        # the explicitly enabled collector starts receiving connection events.
        journal_path = self.output.with_name(self.output.stem + ".raw_ingress.jsonl")
        self.raw_ingress_journal = raw_ingress_journal or RawIngressJournalV1(journal_path)

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _raw_bytes(message: Any) -> bytes:
        if isinstance(message, bytes):
            return message
        if isinstance(message, str):
            # websocket-client returns decoded text frames as str; this preserves
            # the callback text representation, not independent wire-level bytes.
            return message.encode("utf-8", errors="surrogatepass")
        raise TypeError("websocket message must be str or bytes")

    def _journal(
        self, *, event_type: str, verdict: str, generation: int,
        raw_bytes: bytes | None = None, reason_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.raw_ingress_journal.append(
            event_type=event_type,
            received_at_utc=_now(),
            receive_monotonic_ns=time.monotonic_ns(),
            connection_generation=generation,
            verdict=verdict,
            reason_code=reason_code,
            raw_bytes=raw_bytes,
            details=details or {},
        )

    def _process_message(self, message: Any, *, generation: int) -> None:
        """Journal every callback payload before any output handoff or filtering."""
        raw_bytes = self._raw_bytes(message)
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        try:
            payload = json.loads(message)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, RecursionError) as exc:
            self._journal(
                event_type="FRAME", verdict="REJECTED", generation=generation,
                raw_bytes=raw_bytes, reason_code="JSON_DECODE_ERROR",
                details={"raw_frame_sha256": raw_sha256, "error_type": type(exc).__name__},
            )
            return

        if not isinstance(payload, dict):
            self._journal(
                event_type="FRAME", verdict="REJECTED", generation=generation,
                raw_bytes=raw_bytes, reason_code="ENVELOPE_NOT_OBJECT",
                details={"raw_frame_sha256": raw_sha256},
            )
            return

        event_type = str(payload.get("type", payload.get("event", ""))).lower()
        if "order" in event_type:
            self._journal(
                event_type="FRAME", verdict="IGNORED", generation=generation,
                raw_bytes=raw_bytes, reason_code="ORDER_EVENT",
                details={"raw_frame_sha256": raw_sha256},
            )
            return

        try:
            record = normalize_trade(payload)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self._journal(
                event_type="FRAME", verdict="REJECTED", generation=generation,
                raw_bytes=raw_bytes, reason_code="TRADE_NORMALIZATION_ERROR",
                details={"raw_frame_sha256": raw_sha256, "error_type": type(exc).__name__},
            )
            return

        if record is None:
            has_trade_shape = any(
                key in payload for key in ("trade", "data", "symbol", "s", "price", "p")
            )
            self._journal(
                event_type="FRAME",
                verdict="REJECTED" if has_trade_shape else "IGNORED",
                generation=generation,
                raw_bytes=raw_bytes,
                reason_code="TRADE_SCHEMA_INVALID" if has_trade_shape else "UNSUPPORTED_ENVELOPE",
                details={"raw_frame_sha256": raw_sha256},
            )
            return

        sequence = record["sequence"]
        if self.last_sequence is not None and sequence <= self.last_sequence:
            self._journal(
                event_type="FRAME", verdict="IGNORED", generation=generation,
                raw_bytes=raw_bytes, reason_code="NON_MONOTONIC_SEQUENCE",
                details={
                    "raw_frame_sha256": raw_sha256,
                    "sequence_value": sequence,
                    "sequence_semantics": "OPAQUE_UNVERIFIED",
                },
            )
            return

        # A durable journal append must succeed before normalized output is written.
        self._journal(
            event_type="FRAME", verdict="ACCEPTED", generation=generation,
            raw_bytes=raw_bytes,
            details={
                "raw_frame_sha256": raw_sha256,
                "symbol": record["symbol"],
                "sequence_value": sequence,
                "sequence_semantics": "OPAQUE_UNVERIFIED",
            },
        )
        try:
            self._append(record)
        except Exception as exc:
            self._journal(
                event_type="HANDOFF_FAILURE", verdict="REJECTED", generation=generation,
                raw_bytes=raw_bytes, reason_code="OUTPUT_PERSISTENCE_FAILED",
                details={"raw_frame_sha256": raw_sha256, "error_type": type(exc).__name__},
            )
            raise
        self.last_sequence = sequence

    def run(self, *, run_seconds: int = 0) -> None:
        if not self.enabled:
            raise RuntimeError("Forward Tabdeal collector is disabled by default.")

        started = time.monotonic()
        generation = 0

        while run_seconds == 0 or time.monotonic() - started < run_seconds:
            ws = None
            generation += 1
            connection_error: Exception | None = None
            try:
                ws = websocket.create_connection(WS_URL, timeout=15)
                ws.send(SYMBOL)
                self._journal(
                    event_type="CONNECTED", verdict="ACCEPTED", generation=generation,
                    details={"subscription": SYMBOL},
                )

                while run_seconds == 0 or time.monotonic() - started < run_seconds:
                    # Catch only socket receive failures here. Message processing,
                    # journaling, and output persistence failures must escape and
                    # stop the collector rather than being mistaken for disconnects.
                    try:
                        message = ws.recv()
                    except Exception as exc:
                        connection_error = exc
                        break
                    if message is None:
                        break
                    self._process_message(message, generation=generation)

            except Exception as exc:
                # Setup/send failures are connection failures. Failures from
                # journal writes occur here too and must not trigger reconnect.
                if isinstance(exc, OSError):
                    raise
                connection_error = exc
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

            if connection_error is not None:
                self._journal(
                    event_type="CONNECTION_ERROR", verdict="CONNECTION_ERROR",
                    generation=generation, reason_code="COLLECTOR_CONNECTION_ERROR",
                    details={"error_type": type(connection_error).__name__},
                )
            self._journal(
                event_type="DISCONNECT", verdict="DISCONNECTED",
                generation=generation, reason_code="CONNECTION_ENDED",
            )

            if run_seconds and time.monotonic() - started >= run_seconds:
                break
            time.sleep(2)
