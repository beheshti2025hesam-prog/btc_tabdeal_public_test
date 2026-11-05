"""Branch-safe, observation-only Tabdeal collector.

Tabdeal's 2026-11-04 written clarification states that trade.sequence is
informational only: it is not a unique trade ID, ordering guarantee,
deduplication key, replay cursor, or gap detector. The collector preserves
full wire payloads and timestamps but remains disabled by default. The
Broadcast feed has no documented replay/gap recovery; reconnect/resubscribe
alone is not decision-grade and REST snapshot reconciliation is not implemented.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websocket

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
DEFAULT_OUTPUT = "data/forward/observations.jsonl"
SEQUENCE_SEMANTICS = (
    "INFORMATIONAL_ONLY_NOT_UNIQUE_AT_ANY_SCOPE_NOT_ORDERED_"
    "NOT_CONSECUTIVE_NOT_REPLAYABLE_NOT_A_GAP_DETECTOR"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_sequence(value: Any) -> str | int | None:
    # bool is deliberately excluded even though bool subclasses int in Python.
    if type(value) in (str, int):
        return value
    return None


def _raw_payload_evidence(
    payload: dict[str, Any], raw_message: str | bytes | None
) -> tuple[str, str, bytes]:
    if raw_message is None:
        text = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        )
        raw_bytes = text.encode("utf-8")
        return text, "utf-8", raw_bytes
    if isinstance(raw_message, bytes):
        try:
            text = raw_message.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = base64.b64encode(raw_message).decode("ascii")
            encoding = "base64"
        return text, encoding, raw_message
    if isinstance(raw_message, str):
        return raw_message, "utf-8", raw_message.encode("utf-8")
    raise TypeError("raw_message must be str, bytes, or None")


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def normalize_trade(
    payload: dict[str, Any],
    *,
    raw_message: str | bytes | None = None,
    received_at: str | None = None,
) -> dict[str, Any] | None:
    """Preserve a trade envelope even when fields are incomplete.

    The original wire payload and its exact-byte hash are authoritative.
    Normalized fields are convenience metadata only and never make this
    record decision-grade.
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

    symbol = data.get("symbol") or data.get("s")
    price = data.get("price") if "price" in data else data.get("p")
    amount = data.get("amount") if "amount" in data else data.get("q")
    sequence = data.get("sequence") if "sequence" in data else data.get("seq")
    side = data.get("side") or data.get("side_name") or data.get("S")
    event_timestamp = data.get("updated")
    raw_payload, raw_encoding, raw_bytes = _raw_payload_evidence(payload, raw_message)
    received = received_at or _now()

    reason_codes: list[str] = []
    if not isinstance(symbol, str) or not symbol.strip():
        reason_codes.append("MARKET_MISSING")
    elif symbol != SYMBOL:
        reason_codes.append("MARKET_MISMATCH")
    if price is None:
        reason_codes.append("PRICE_MISSING")
    elif _finite_float(price) is None:
        reason_codes.append("PRICE_INVALID")
    if amount is None:
        reason_codes.append("AMOUNT_MISSING")
    elif _finite_float(amount) is None:
        reason_codes.append("AMOUNT_INVALID")
    if event_timestamp is None:
        reason_codes.append("EVENT_TIMESTAMP_MISSING")

    return {
        "observed_at": received,  # compatibility alias for prior observation records
        "received_at": received,
        "event_timestamp": event_timestamp,  # preserve the venue's original value/type
        "event_timestamp_field": "trade.updated" if event_timestamp is not None else None,
        "source_updated": str(event_timestamp) if event_timestamp is not None else None,
        "sequence_scope": "UNSPECIFIED_NO_GLOBAL_PER_MARKET_OR_PER_CONNECTION_IDENTITY",
        "depth_sequence_policy": "INDEPENDENT_SEPARATE_FIELD_NO_COMPARISON_WITH_TRADE_SEQUENCE",
        "market": symbol if isinstance(symbol, str) else None,
        "symbol": symbol if isinstance(symbol, str) else None,
        "price": _finite_float(price),
        "price_raw": str(price) if price is not None else None,
        "amount": _finite_float(amount),
        "amount_raw": str(amount) if amount is not None else None,
        "side": str(side) if side is not None else "UNKNOWN",
        "sequence_raw": _opaque_sequence(sequence),
        "sequence_semantics": SEQUENCE_SEMANTICS,
        "raw_payload": raw_payload,
        "raw_payload_encoding": raw_encoding,
        "raw_payload_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "normalization_status": "VALID" if not reason_codes else "INCOMPLETE_RAW_PRESERVED",
        "reason_codes": reason_codes,
        "recovery_status": "RECONNECT_RESUBSCRIBE_ONLY_NO_DOCUMENTED_REPLAY_OR_GAP_RECOVERY",
        "snapshot_reconciliation_status": "NOT_IMPLEMENTED",
        "decision_grade": False,
        "source": "tabdeal_ws_forward_v1",
    }


class ForwardTabdealCollectorV1:
    def __init__(self, output: str = DEFAULT_OUTPUT, *, enabled: bool = False) -> None:
        self.output = Path(output)
        self.enabled = enabled
        self.connection_epoch: str | None = None
        self.receive_ordinal = 0

    def _append(self, record: dict[str, Any]) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run(self, *, run_seconds: int = 0) -> None:
        if not self.enabled:
            raise RuntimeError("Forward Tabdeal collector is disabled by default.")
        started = time.monotonic()
        while run_seconds == 0 or time.monotonic() - started < run_seconds:
            ws = None
            try:
                ws = websocket.create_connection(WS_URL, timeout=15)
                ws.send(SYMBOL)
                self.connection_epoch = str(uuid.uuid4())
                self.receive_ordinal = 0
                while run_seconds == 0 or time.monotonic() - started < run_seconds:
                    message = ws.recv()
                    if not message:
                        break
                    received_at = _now()
                    try:
                        payload = json.loads(message)
                    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                        continue
                    record = normalize_trade(
                        payload, raw_message=message, received_at=received_at
                    )
                    if record is None:
                        continue
                    # Arrival order is local evidence only, never venue sequence order.
                    self.receive_ordinal += 1
                    record["connection_epoch"] = self.connection_epoch
                    record["receive_ordinal"] = self.receive_ordinal
                    self._append(record)
            except Exception:
                # Reconnect/resubscribe only. No replay or gap recovery is claimed.
                pass
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
            if run_seconds and time.monotonic() - started >= run_seconds:
                break
            time.sleep(2)