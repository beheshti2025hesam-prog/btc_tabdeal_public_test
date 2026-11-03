#!/usr/bin/env python3
"""Fail-closed integrity witness for the Gate.io 1m feed soak."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("HES_GLOBAL_MARKET_DATA_ROOT", "/opt/hes-trade-agent")).expanduser()
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from forward.global_market_data_reader_v1 import read_closed_candles

FEED = DATA_ROOT / "data/forward/global_market_candles_1m_v1.jsonl"
EVIDENCE = Path(os.environ.get(
    "HES_GATEIO_1M_INTEGRITY_STATE",
    "/var/lib/hes-gateio-1m-integrity/observations.jsonl",
))
now = int(time.time())
record = {
    "schema": "hes_gateio_1m_integrity_observation_v1",
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "service": "hes-global-market-data-gateio-1m.service",
    "source": "gateio_public_spot",
    "symbol": "BTC_USDT",
    "timeframe": "1m",
    "status": "BLOCKED",
    "reason_codes": [],
    "execution_enabled": False,
    "orders_placed": False,
}
try:
    if FEED.is_symlink() or not FEED.is_file():
        raise RuntimeError("FEED_FILE_MISSING_OR_SYMLINK")
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "hes-global-market-data-gateio-1m.service"],
        timeout=5, check=False,
    ).returncode == 0
    if not active:
        raise RuntimeError("FEED_SERVICE_NOT_ACTIVE")
    rows = read_closed_candles("1m", root=DATA_ROOT, now=now, min_bars=200)
    latest = rows[-1]
    age = now - int(latest["close_time"])
    if age < 0 or age > 120:
        raise RuntimeError("FEED_STALE")
    record.update(
        status="PASS",
        reason_codes=[],
        closed_candles=len(rows),
        first_open_time=rows[0]["open_time"],
        latest_open_time=latest["open_time"],
        latest_close_time=latest["close_time"],
        latest_age_seconds=age,
        feed_bytes=FEED.stat().st_size,
        feed_sha256=hashlib.sha256(FEED.read_bytes()).hexdigest(),
    )
except Exception as exc:
    allowed = {
        "FEED_FILE_MISSING_OR_SYMLINK", "FEED_SERVICE_NOT_ACTIVE", "FEED_STALE",
        "CANDLE_FILE_MISSING", "CANDLE_FILE_UNREADABLE", "INSUFFICIENT_CLOSED_CANDLES",
        "SOURCE_IDENTITY_MISMATCH", "OPEN_CANDLE_REJECTED", "CANDLE_INTERVAL_GAP",
        "CANDLE_ORDER_OR_DUPLICATE", "CANDLE_FEED_STALE", "CANDLE_CLOSE_IN_FUTURE",
        "CANDLE_OHLC_INVALID", "CANDLE_SCHEMA_INVALID", "CANDLE_NON_FINITE_VALUE",
        "CANDLE_QUOTE_VOLUME_INVALID", "CANDLE_TIMESTAMP_ALIGNMENT_INVALID",
    }
    record["reason_codes"] = [str(exc) if str(exc) in allowed else type(exc).__name__]

EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(
    EVIDENCE,
    os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
try:
    os.write(fd, (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.fsync(fd)
finally:
    os.close(fd)

print(json.dumps(record, sort_keys=True))
if record["status"] != "PASS":
    raise SystemExit(1)
