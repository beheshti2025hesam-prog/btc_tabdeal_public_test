"""Read-only diagnostic for Binance public server time vs latest BTCUSDT candle.

No credentials, trading endpoints, account access, or order placement.
Exit non-zero on implausible clock skew, future candle open time, or stale data.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from dataclasses import dataclass

SPOT_BASE = "https://data-api.binance.vision"
FUTURES_BASE = "https://fapi.binance.com"
MAX_SKEW_MS = 5_000
MAX_CANDLE_AGE_MS = 180_000
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ProbeResult:
    venue: str
    server_time_ms: int
    candle_open_time_ms: int
    local_midpoint_ms: int
    server_local_skew_ms: int
    candle_age_ms: int


def get_json(url: str) -> object:
    request = urllib.request.Request(
        url, headers={"User-Agent": "HES-public-clock-probe/1.0"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return json.load(response)


def probe(venue: str, base_url: str, time_path: str, kline_path: str) -> ProbeResult:
    before = time.time_ns() // 1_000_000
    server_payload = get_json(base_url + time_path)
    after = time.time_ns() // 1_000_000
    midpoint = (before + after) // 2

    if not isinstance(server_payload, dict) or not isinstance(server_payload.get("serverTime"), int):
        raise ValueError(f"{venue}: invalid server-time payload")
    server_time = server_payload["serverTime"]
    skew = server_time - midpoint
    if abs(skew) > MAX_SKEW_MS:
        raise RuntimeError(f"{venue}: server/local clock skew {skew} ms exceeds {MAX_SKEW_MS} ms")

    candles = get_json(base_url + kline_path)
    if not isinstance(candles, list) or not candles or not isinstance(candles[0], list):
        raise ValueError(f"{venue}: invalid kline payload")
    candle_open = candles[-1][0]
    if not isinstance(candle_open, int):
        raise ValueError(f"{venue}: candle open timestamp is not an integer")

    age = server_time - candle_open
    result = ProbeResult(venue, server_time, candle_open, midpoint, skew, age)

    if age < 0:
        raise RuntimeError(f"{venue}: latest candle opens in the future by {-age} ms")
    if age > MAX_CANDLE_AGE_MS:
        raise RuntimeError(f"{venue}: latest 1m candle is stale by {age} ms")

    return result


def main() -> int:
    targets = [
        ("binance_spot", SPOT_BASE, "/api/v3/time", "/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=2"),
        ("binance_usdm", FUTURES_BASE, "/fapi/v1/time", "/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=2"),
    ]
    failures = 0
    for target in targets:
        try:
            result = probe(*target)
            print(json.dumps(result.__dict__, sort_keys=True))
        except Exception as exc:  # diagnostics must report both venues independently
            failures += 1
            print(json.dumps({"venue": target[0], "status": "FAIL_CLOSED", "error": str(exc)}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
