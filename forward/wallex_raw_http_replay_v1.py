"""Replay exact Wallex raw HTTP response bytes through the same parser."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .wallex_native_candles_v1 import parse_history, RESOLUTION_SECONDS
    from .wallex_raw_http_evidence_v1 import verify_raw_http_response_v1
except ImportError:
    from wallex_native_candles_v1 import parse_history, RESOLUTION_SECONDS
    from wallex_raw_http_evidence_v1 import verify_raw_http_response_v1


TIMEFRAME_BY_RESOLUTION = {"1": "1m", "60": "1h", "1D": "1D"}


class RawResponseReplayError(ValueError):
    """Raw evidence cannot reproduce a bounded, verified native candle set."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _candle_payload(candle: Any) -> dict[str, Any]:
    return {
        "venue": candle.venue,
        "symbol": candle.symbol,
        "resolution": candle.resolution,
        "timeframe": TIMEFRAME_BY_RESOLUTION[candle.resolution],
        "open_time": candle.open_time.isoformat(),
        "close_time": candle.close_time.isoformat(),
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "source_timestamp": candle.source_timestamp,
        "source_observed_at": candle.source_observed_at.isoformat(),
    }


def replay_raw_http_response_v1(
    path: str | Path,
    *,
    as_of: datetime,
    expected_candle_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify raw bytes, replay the parser, and require exact expected candle hashes."""
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise RawResponseReplayError("as_of must be timezone-aware")
    if not isinstance(expected_candle_records, list):
        raise RawResponseReplayError("expected candle records must be a list")

    evidence = verify_raw_http_response_v1(path)
    params = evidence["request_params"]
    required = {"symbol", "resolution", "from", "to"}
    if set(params) != required:
        raise RawResponseReplayError("request parameters do not match the bounded history contract")
    if not isinstance(params["symbol"], str) or not params["symbol"]:
        raise RawResponseReplayError("invalid request symbol")
    resolution = params["resolution"]
    if resolution not in RESOLUTION_SECONDS:
        raise RawResponseReplayError("unsupported native resolution in raw request")
    for key in ("from", "to"):
        if type(params[key]) is not int:
            raise RawResponseReplayError(f"request {key} must be an integer Unix timestamp")
    if params["to"] <= params["from"]:
        raise RawResponseReplayError("invalid request range")

    try:
        payload = json.loads(evidence["raw_body"], parse_float=Decimal)
        # Match fetch_history's request-boundary check over the full raw source
        # timestamp set, including open candles that parse_history omits.
        if isinstance(payload, dict) and payload.get("s") == "ok":
            source_times = payload.get("t")
            if isinstance(source_times, list):
                for ts in source_times:
                    if type(ts) is int and (ts < params["from"] or ts > params["to"]):
                        raise RawResponseReplayError("raw response contains source timestamps outside the requested time range")
        observed_at = datetime.fromisoformat(evidence["received_at"].replace("Z", "+00:00"))
        candles = parse_history(
            payload,
            symbol=params["symbol"],
            resolution=resolution,
            as_of=as_of,
            observed_at=observed_at,
        )
    except RawResponseReplayError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RawResponseReplayError(f"raw response replay rejected: {type(exc).__name__}") from None

    if any(c.source_timestamp < params["from"] or c.source_timestamp > params["to"] for c in candles):
        raise RawResponseReplayError("response contains candles outside the requested time range")

    actual_records = []
    for candle in candles:
        body = _candle_payload(candle)
        actual_records.append({**body, "canonical_candle_sha256": hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()})

    expected_hashes = [item.get("canonical_candle_sha256") for item in expected_candle_records if isinstance(item, dict)]
    if len(expected_hashes) != len(expected_candle_records):
        raise RawResponseReplayError("expected candle record list contains invalid entries")
    actual_hashes = [item["canonical_candle_sha256"] for item in actual_records]
    if actual_hashes != expected_hashes:
        raise RawResponseReplayError("raw replay candle set does not match the expected observation")
    for actual, expected in zip(actual_records, expected_candle_records):
        for field, value in actual.items():
            if expected.get(field) != value:
                raise RawResponseReplayError(f"raw replay mismatch in field: {field}")

    return {
        "schema": "HES_WALLEX_RAW_HTTP_REPLAY_V1",
        "status": "RAW_REPLAY_VERIFIED",
        "evidence_envelope_sha256": evidence["evidence_envelope_sha256"],
        "raw_body_sha256": evidence["raw_body_sha256"],
        "symbol": params["symbol"],
        "resolution": resolution,
        "timeframe": TIMEFRAME_BY_RESOLUTION[resolution],
        "request_from": params["from"],
        "request_to": params["to"],
        "as_of": as_of.isoformat(),
        "candle_count": len(actual_records),
        "canonical_candle_sha256": actual_hashes,
        "raw_source_replay_verified": True,
        "signal_generated": False,
        "trade_decision_generated": False,
        "execution_enabled": False,
    }
