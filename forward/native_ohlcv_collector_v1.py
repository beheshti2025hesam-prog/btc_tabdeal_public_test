"""Disabled-by-default durable collector for native venue OHLCV candles.

One explicit call fetches one bounded batch. No background loop, Git writes,
credential handling, strategy, or order execution exists in this module.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

from .native_ohlcv_v1 import NativeOHLCVBatch, NativeOHLCVSource, validate_native_batch

DEFAULT_OUTPUT = "data/forward/native_ohlcv_batches.jsonl"


class NativeOHLCVCollectorV1:
    """Append-only, one-batch collector. Disabled unless explicitly opted in."""

    def __init__(
        self,
        *,
        source: NativeOHLCVSource,
        output: str | Path = DEFAULT_OUTPUT,
        enabled: bool = False,
    ) -> None:
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        self.source = source
        self.output = Path(output)
        self.enabled = enabled
        self.lock_path = self.output.with_name(self.output.name + ".lock")

    def collect_once(
        self,
        *,
        symbol: str,
        interval: str = "15m",
        limit: int = 100,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Native OHLCV collector is disabled by default.")
        batch: NativeOHLCVBatch = self.source.fetch(
            symbol=symbol, interval=interval, limit=limit,
            start_time_ms=start_time_ms, end_time_ms=end_time_ms,
            as_of_ms=as_of_ms,
        )
        validate_native_batch(batch)
        record: dict[str, Any] = {
            "artifact_type": "NATIVE_OHLCV_BATCH",
            "schema_version": 1,
            "venue": batch.venue,
            "product": batch.product,
            "symbol": batch.symbol,
            "interval": batch.interval,
            "endpoint_kind": batch.endpoint_kind,
            "fetched_at_ms": batch.fetched_at_ms,
            "response_sha256": batch.response_sha256,
            "open_candles_excluded": batch.open_candles_excluded,
            "candles": [
                {
                    "open_time_ms": candle.open_time_ms,
                    "close_time_ms": candle.close_time_ms,
                    "open": str(candle.open),
                    "high": str(candle.high),
                    "low": str(candle.low),
                    "close": str(candle.close),
                    "volume": str(candle.volume),
                    "quote_volume": str(candle.quote_volume),
                    "trade_count": candle.trade_count,
                    "taker_buy_volume": str(candle.taker_buy_volume),
                    "taker_buy_quote_volume": str(candle.taker_buy_quote_volume),
                    "closed": candle.closed,
                }
                for candle in batch.candles
            ],
            "gaps": [
                {
                    "expected_open_time_ms": gap.expected_open_time_ms,
                    "next_observed_open_time_ms": gap.next_observed_open_time_ms,
                    "missing_intervals": gap.missing_intervals,
                }
                for gap in batch.gaps
            ],
            "execution": "OFF",
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                # Never append behind a truncated JSONL tail from a prior crash.
                if self.output.exists() and self.output.stat().st_size:
                    with self.output.open("rb") as existing:
                        existing.seek(-1, os.SEEK_END)
                        if existing.read(1) != b"\n":
                            raise RuntimeError("native OHLCV journal has an incomplete trailing record")
                fd = os.open(self.output, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
                try:
                    data = line.encode("utf-8")
                    original_size = os.fstat(fd).st_size
                    try:
                        offset = 0
                        while offset < len(data):
                            written = os.write(fd, data[offset:])
                            if written <= 0:
                                raise OSError("native OHLCV write made no progress")
                            offset += written
                        os.fsync(fd)
                    except Exception:
                        # Roll back a partial write while the process still owns
                        # the lock; do not leave a corrupt tail for later appends.
                        os.ftruncate(fd, original_size)
                        os.fsync(fd)
                        raise
                finally:
                    os.close(fd)
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return record
