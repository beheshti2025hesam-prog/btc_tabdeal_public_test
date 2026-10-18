"""Read-only CI probe for Wallex native OHLCV; writes raw response and a hash manifest."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

from forward.native_wallex_ohlcv_v1 import fetch_native_ohlcv_evidence


def main() -> int:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=10)
    evidence = fetch_native_ohlcv_evidence(
        symbol="BTCUSDT",
        timeframe_minutes=1,
        start=start,
        end=now,
        as_of=now,
        timeout_seconds=15,
    )
    out = Path("artifacts/native-wallex-ohlcv")
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw-response.json").write_bytes(evidence.raw_response)

    candles = evidence.candles
    if not candles:
        raise RuntimeError("Wallex returned no candles for BTCUSDT/1m")
    closed = [c for c in candles if c.is_closed]
    latest_closed = closed[-1] if closed else None
    age_seconds = (now - latest_closed.close_time).total_seconds() if latest_closed else None
    gaps = []
    for left, right in zip(candles, candles[1:]):
        delta = int((right.open_time - left.open_time).total_seconds())
        if delta != 60:
            gaps.append({"after": left.open_time.isoformat(), "before": right.open_time.isoformat(), "delta_seconds": delta})

    manifest = {
        "source": "wallex_native_udf_history",
        "endpoint": "https://api.wallex.ir/v1/udf/history",
        "request_url": evidence.request_url,
        "symbol": "BTCUSDT",
        "resolution": "1",
        "requested_from_utc": start.isoformat(),
        "requested_to_utc": now.isoformat(),
        "retrieved_at_utc": evidence.retrieved_at.isoformat(),
        "raw_response_sha256": evidence.raw_sha256,
        "raw_response_bytes": len(evidence.raw_response),
        "returned_candle_count": len(candles),
        "first_open_time_utc": candles[0].open_time.isoformat(),
        "last_open_time_utc": candles[-1].open_time.isoformat(),
        "latest_closed_candle_close_utc": latest_closed.close_time.isoformat() if latest_closed else None,
        "latest_closed_candle_age_seconds": age_seconds,
        "observed_gaps": gaps,
        "note": "Read-only public market-data probe; no credentials, account access, collector activation, or orders.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

    if len(candles) < 3:
        raise RuntimeError("fewer than three candles returned in the 10-minute probe window")
    if latest_closed is None or age_seconds is None or age_seconds > 300:
        raise RuntimeError("latest closed candle is stale (SLA: <= 300 seconds)")
    if gaps:
        raise RuntimeError("gap detected in native OHLCV probe window; see manifest")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"native Wallex OHLCV probe failed: {exc}", file=sys.stderr)
        raise
