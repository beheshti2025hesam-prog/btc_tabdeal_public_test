"""Candle-first, read-only Wallex observation journal.

This path deliberately does not feed the legacy BTC_USDT/15m trade-sequence
consumer: the verified Wallex native resolutions are 1m, 1h and 1D, while that
consumer requires BTC_USDT/15m and integer sequence IDs. Missing intervals are
recorded as gaps and block feature promotion; no candles are synthesized.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from forward.wallex_native_candles_v1 import NativeCandle, RESOLUTION_SECONDS


class WallexObservationError(ValueError):
    """Unsafe or unverifiable candle observation input/journal."""


TIMEFRAME_BY_RESOLUTION = {"1": "1m", "60": "1h", "1D": "1D"}
LEGACY_FEATURE_CONTRACT = {"symbol": "BTC_USDT", "timeframe": "15m", "sequence": "required"}


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WallexObservationError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _candle_payload(candle: NativeCandle) -> dict[str, Any]:
    return {
        "venue": candle.venue,
        "symbol": candle.symbol,
        "resolution": candle.resolution,
        "timeframe": TIMEFRAME_BY_RESOLUTION[candle.resolution],
        "open_time": _utc(candle.open_time, "open_time").isoformat(),
        "close_time": _utc(candle.close_time, "close_time").isoformat(),
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "source_timestamp": candle.source_timestamp,
        "source_observed_at": _utc(candle.source_observed_at, "source_observed_at").isoformat(),
    }


class WallexCandleObservationV1:
    """Validate closed native candles and append a tamper-evident observation row."""

    def __init__(self, journal_path: str | Path, *, max_records: int = 100_000):
        if max_records <= 0:
            raise WallexObservationError("max_records must be positive")
        self.path = Path(journal_path)
        self.max_records = max_records

    def _verify_journal(self) -> str | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise WallexObservationError("journal has an incomplete final line")
        previous: str | None = None
        for index, line in enumerate(raw.splitlines(), start=1):
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise WallexObservationError(f"journal line {index} is invalid JSON") from None
            if not isinstance(record, dict):
                raise WallexObservationError(f"journal line {index} is not an object")
            claimed = record.get("record_sha256")
            if not isinstance(claimed, str) or len(claimed) != 64:
                raise WallexObservationError(f"journal line {index} has no valid record hash")
            if record.get("previous_record_sha256") != previous:
                raise WallexObservationError(f"journal chain mismatch at line {index}")
            body = {key: value for key, value in record.items() if key != "record_sha256"}
            actual = _sha256(_canonical(body).encode("utf-8"))
            if actual != claimed:
                raise WallexObservationError(f"journal payload/hash mismatch at line {index}")
            previous = claimed
        return previous

    def observe(
        self,
        candles: Iterable[NativeCandle],
        *,
        as_of: datetime,
        run_id: str,
        max_age_seconds: int,
    ) -> dict[str, Any]:
        as_of = _utc(as_of, "as_of")
        if not isinstance(run_id, str) or not run_id.strip():
            raise WallexObservationError("run_id is required")
        if type(max_age_seconds) is not int or max_age_seconds < 0:
            raise WallexObservationError("max_age_seconds must be a non-negative integer")

        items = list(candles)
        if not items:
            raise WallexObservationError("at least one native candle is required")
        if len(items) > self.max_records:
            raise WallexObservationError("observation record bound exceeded")

        first = items[0]
        if not isinstance(first, NativeCandle):
            raise WallexObservationError("only NativeCandle records are accepted")
        if first.venue != "wallex" or first.resolution not in RESOLUTION_SECONDS:
            raise WallexObservationError("unsupported venue or unverified resolution")
        symbol, resolution = first.symbol, first.resolution
        step = RESOLUTION_SECONDS[resolution]
        normalized: list[tuple[NativeCandle, dict[str, Any]]] = []
        seen: dict[int, str] = {}
        previous_ts: int | None = None
        stale_source_observation = False

        for index, candle in enumerate(items):
            if not isinstance(candle, NativeCandle):
                raise WallexObservationError(f"candles[{index}] is not NativeCandle")
            if candle.venue != "wallex" or candle.symbol != symbol or candle.resolution != resolution:
                raise WallexObservationError("mixed venue, symbol, or timeframe is forbidden")
            payload = _candle_payload(candle)
            open_time = _utc(candle.open_time, "open_time")
            close_time = _utc(candle.close_time, "close_time")
            observed_at = _utc(candle.source_observed_at, "source_observed_at")
            if candle.source_timestamp != int(open_time.timestamp()):
                raise WallexObservationError("source timestamp does not match candle open time")
            if int((close_time - open_time).total_seconds()) != step:
                raise WallexObservationError("candle interval does not match verified resolution")
            if close_time > as_of:
                raise WallexObservationError("open or future candle is forbidden")
            if observed_at < close_time:
                raise WallexObservationError("source observation predates candle close")
            if observed_at > as_of:
                raise WallexObservationError("source observation time is in the future")
            if as_of.timestamp() - observed_at.timestamp() > max_age_seconds:
                stale_source_observation = True
            op, high, low, close, volume = (Decimal(str(getattr(candle, key)))
                                            for key in ("open", "high", "low", "close", "volume"))
            if any(not x.is_finite() for x in (op, high, low, close, volume)):
                raise WallexObservationError("non-finite OHLCV value")
            if min(op, high, low, close) <= 0 or volume < 0:
                raise WallexObservationError("invalid OHLCV value")
            if low > min(op, close) or high < max(op, close) or low > high:
                raise WallexObservationError("OHLC bounds invalid")
            fingerprint = _sha256(_canonical(payload).encode("utf-8"))
            ts = candle.source_timestamp
            if previous_ts is not None and ts < previous_ts:
                raise WallexObservationError("source timestamps are not monotonic")
            if ts in seen:
                if seen[ts] != fingerprint:
                    raise WallexObservationError("conflicting duplicate candle timestamp")
                previous_ts = ts
                continue
            seen[ts] = fingerprint
            previous_ts = ts
            normalized.append((candle, {**payload, "canonical_candle_sha256": fingerprint}))

        gaps: list[dict[str, Any]] = []
        for (_, left), (_, right) in zip(normalized, normalized[1:]):
            left_ts = int(datetime.fromisoformat(left["open_time"]).timestamp())
            right_ts = int(datetime.fromisoformat(right["open_time"]).timestamp())
            if right_ts - left_ts > step:
                gaps.append({
                    "after_open_time": left["open_time"],
                    "before_open_time": right["open_time"],
                    "missing_intervals": (right_ts - left_ts) // step - 1,
                })

        latest_close = max(_utc(c.close_time, "close_time") for c, _ in normalized)
        stale_latest = as_of.timestamp() - latest_close.timestamp() > max_age_seconds
        status = "BLOCKED" if gaps or stale_latest or stale_source_observation else "OBSERVED"
        reasons = []
        if gaps:
            reasons.append("MISSING_INTERVALS")
        if stale_latest:
            reasons.append("LATEST_CANDLE_STALE")
        if stale_source_observation:
            reasons.append("STALE_SOURCE_OBSERVATION")

        # The legacy feature path is deliberately not called: it hard-requires
        # BTC_USDT/15m plus trade sequence IDs, which this native feed does not supply.
        body: dict[str, Any] = {
            "schema": "HES_WALLEX_CANDLE_OBSERVATION_V1",
            "run_id": run_id,
            "observed_at": as_of.isoformat(),
            "venue": "wallex",
            "symbol": symbol,
            "resolution": resolution,
            "timeframe": TIMEFRAME_BY_RESOLUTION[resolution],
            "status": status,
            "reason": "OK" if not reasons else "+".join(reasons),
            "max_age_seconds": max_age_seconds,
            "latest_candle_close_time": latest_close.isoformat(),
            "source_provenance": {
                "timestamps_and_canonical_candle_hashes": "RECORDED",
                "raw_response_bytes_retained": False,
                "raw_response_sha256": None,
                "raw_response_capture_required_before_replay_claim": True,
            },
            "candles": [payload for _, payload in normalized],
            "gaps": gaps,
            "downstream_features": {
                "status": "BLOCKED_CONTRACT_MISMATCH",
                "required": LEGACY_FEATURE_CONTRACT,
                "received": {"symbol": symbol, "timeframe": TIMEFRAME_BY_RESOLUTION[resolution],
                             "sequence": "not provided by native OHLCV"},
                "synthetic_candles_created": False,
            },
        }

        previous_hash = self._verify_journal()
        body["previous_record_sha256"] = previous_hash
        record = {**body, "record_sha256": _sha256(_canonical(body).encode("utf-8"))}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write((_canonical(record) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        return record
