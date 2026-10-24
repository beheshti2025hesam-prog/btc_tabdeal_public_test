"""Export closed BTCUSDT USDⓈ-M futures candles using the existing Binance adapter.

This is an explicit, read-only research-data export. It does not create a new
market-data source implementation, start a collector, or touch execution APIs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from forward.native_ohlcv_v1 import INTERVAL_MS, BinanceUsdMPerpetualKlineSource


def export_binance_ohlcv(*, output_csv: str | Path, manifest_path: str | Path, days: int = 180, interval: str = "15m", now_ms: int | None = None) -> dict:
    if type(days) is not int or not 30 <= days <= 365:
        raise ValueError("days must be an integer between 30 and 365")
    if interval not in INTERVAL_MS:
        raise ValueError("unsupported interval")
    observed_now = int(time.time() * 1000) if now_ms is None else now_ms
    if type(observed_now) is not int or observed_now <= 0:
        raise ValueError("now_ms must be a positive integer")
    interval_ms = INTERVAL_MS[interval]
    start_ms = ((observed_now - days * 86_400_000) // interval_ms) * interval_ms
    as_of_ms = observed_now
    end_ms = observed_now - 1
    source = BinanceUsdMPerpetualKlineSource()
    cursor = start_ms
    candles = []
    response_hashes: list[str] = []
    request_count = 0
    last_open = None

    while cursor <= end_ms:
        request_count += 1
        if request_count > 200:
            raise RuntimeError("pagination safety limit reached")
        batch = source.fetch(
            symbol="BTCUSDT", interval=interval, limit=1500,
            start_time_ms=cursor, end_time_ms=end_ms, as_of_ms=as_of_ms,
        )
        response_hashes.append(batch.response_sha256)
        if batch.gaps:
            raise ValueError(f"source candle gaps detected in page: {batch.gaps!r}")
        if not batch.candles:
            break
        for candle in batch.candles:
            if last_open is not None and candle.open_time_ms != last_open + interval_ms:
                raise ValueError("non-contiguous candles across pagination boundary")
            candles.append(candle)
            last_open = candle.open_time_ms
        next_cursor = last_open + interval_ms
        if next_cursor <= cursor:
            raise RuntimeError("pagination made no progress")
        cursor = next_cursor
        if len(batch.candles) < 1500:
            break

    if len(candles) < 1000:
        raise ValueError(f"insufficient closed candles for research candidate: {len(candles)}")
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "open", "high", "low", "close", "volume"))
        writer.writeheader()
        for candle in candles:
            # Use exclusive close time so each timestamp means the candle is complete.
            timestamp = datetime.fromtimestamp((candle.close_time_ms + 1) / 1000, tz=timezone.utc).isoformat()
            writer.writerow({
                "timestamp": timestamp,
                "open": str(candle.open),
                "high": str(candle.high),
                "low": str(candle.low),
                "close": str(candle.close),
                "volume": str(candle.volume),
            })

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "status": "RESEARCH_DATASET_NOT_PROMOTED",
        "source_id": "binance-usdm-perpetual-public-klines",
        "venue": "binance",
        "product": "usdm_perpetual",
        "symbol": "BTCUSDT",
        "interval": interval,
        "requested_days": days,
        "as_of_ms": as_of_ms,
        "first_candle_close_time": datetime.fromtimestamp((candles[0].close_time_ms + 1) / 1000, tz=timezone.utc).isoformat(),
        "last_candle_close_time": datetime.fromtimestamp((candles[-1].close_time_ms + 1) / 1000, tz=timezone.utc).isoformat(),
        "closed_candles": len(candles),
        "request_count": request_count,
        "response_sha256_by_page": response_hashes,
        "dataset_csv_sha256": digest,
        "source_endpoint": "https://fapi.binance.com/fapi/v1/klines",
        "read_only_public_data": True,
        "execution_or_orders": False,
    }
    target_manifest = Path(manifest_path)
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--output-csv", default="data/transformer-training/btcusdt_usdm_15m.csv")
    parser.add_argument("--manifest", default="data/transformer-training/source_manifest.json")
    args = parser.parse_args(argv)
    print(json.dumps(export_binance_ohlcv(
        output_csv=args.output_csv, manifest_path=args.manifest,
        days=args.days, interval=args.interval,
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
