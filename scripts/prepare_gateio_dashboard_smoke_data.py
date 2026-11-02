#!/usr/bin/env python3
"""CI-only live Gate.io fixture writer for the persisted-reader dashboard smoke."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from forward.native_ohlcv_gateio_v1 import GateioSpotKlineSource
from forward.native_ohlcv_v1 import INTERVAL_MS, validate_native_batch

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = {
    "15m": ROOT / "data/forward/global_market_candles_v1.jsonl",
    "1h": ROOT / "data/forward/global_market_candles_1h_v1.jsonl",
    "4h": ROOT / "data/forward/global_market_candles_4h_v1.jsonl",
}


def main() -> None:
    if os.environ.get("CI") != "true" or os.environ.get("HES_DASHBOARD_SMOKE_FIXTURE") != "1":
        raise SystemExit("refusing to write fixture data outside explicit CI smoke mode")
    source = GateioSpotKlineSource()
    for interval, output in OUTPUTS.items():
        batch = source.fetch(symbol="BTCUSDT", interval=interval, limit=240)
        validate_native_batch(batch)
        if len(batch.candles) < 200 or batch.gaps:
            raise RuntimeError(f"insufficient or discontinuous live Gate.io candles for {interval}")
        observed_at = datetime.now(timezone.utc).isoformat()
        seconds = INTERVAL_MS[interval] // 1000
        records = []
        for candle in batch.candles:
            open_time = candle.open_time_ms // 1000
            records.append({
                "schema": "hes_global_candle_v1",
                "source": "gateio_public_spot",
                "symbol": "BTC_USDT",
                "timeframe": interval,
                "open_time": open_time,
                "close_time": open_time + seconds,
                "open": str(candle.open),
                "high": str(candle.high),
                "low": str(candle.low),
                "close": str(candle.close),
                "volume": str(candle.volume),
                "quote_volume": str(candle.quote_volume),
                "closed": True,
                "observed_at": observed_at,
                "source_response_sha256": batch.response_sha256,
            })
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in records),
                          encoding="utf-8")
        print(json.dumps({"interval": interval, "rows": len(records),
                          "source_response_sha256": batch.response_sha256,
                          "output": str(output.relative_to(ROOT))}, sort_keys=True))


if __name__ == "__main__":
    main()
