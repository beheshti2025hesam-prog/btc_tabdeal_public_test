#!/usr/bin/env python3
"""Per-run 24h read-only Gate.io soak with 1m coverage and immutable release provenance."""
import fcntl
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET_DATA_ROOT = Path(os.environ.get("HES_GLOBAL_MARKET_DATA_ROOT", str(ROOT))).expanduser()
sys.path.insert(0, str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input, read_closed_candles

SERVICES = (
    "hes-global-market-data-gateio.service",
    "hes-global-market-data-gateio-1m.service",
    "hes-global-market-data-gateio-1m-integrity.timer",
    "hes-global-market-data-gateio-1h.service",
    "hes-global-market-data-gateio-4h.service",
)
TIMEFRAME_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
MAX_AGE_SECONDS = {"1m": 120, "15m": 1080, "1h": 3780, "4h": 14580}
DURATION = 24 * 60 * 60
INTERVAL = 60
LOG = Path(os.environ.get(
    "HES_GATEIO_SOAK_LOG",
    str(ROOT / "data/forward/gateio_feed_soak_24h_v2.jsonl"),
)).expanduser()


def release_provenance(*, root: str | Path = ROOT, script_path: str | Path | None = None) -> dict[str, str]:
    release_root = Path(root).resolve()
    manifest_path = release_root / "HES_RELEASE_MANIFEST_v1.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    commit_sha = manifest.get("commit_sha")
    if (
        not isinstance(commit_sha, str)
        or len(commit_sha) != 40
        or commit_sha != release_root.name
    ):
        raise ValueError("SOAK_RELEASE_ID_MISMATCH")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    sidecar_path = release_root / "HES_RELEASE_MANIFEST_v1.sha256"
    sidecar_fields = sidecar_path.read_text(encoding="utf-8").strip().split()
    if (
        len(sidecar_fields) < 2
        or sidecar_fields[0] != manifest_sha256
        or sidecar_fields[-1] != "HES_RELEASE_MANIFEST_v1.json"
    ):
        raise ValueError("SOAK_RELEASE_MANIFEST_SIDECAR_MISMATCH")
    source_script = Path(script_path or __file__).resolve()
    if not source_script.is_file():
        raise ValueError("SOAK_SCRIPT_MISSING")
    return {
        "code_release_id": commit_sha,
        "release_manifest_sha256": manifest_sha256,
        "soak_script_sha256": hashlib.sha256(source_script.read_bytes()).hexdigest(),
    }


def sample(seq: int, start: float, run_id: str, release: dict[str, str]) -> dict:
    rec = {
        "schema": "hes_gateio_soak_sample_v3",
        "run_id": run_id,
        "sample": seq,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": int(time.monotonic() - start),
        **release,
        "execution_enabled": False,
        "orders_placed": False,
    }
    try:
        data = load_market_input(root=MARKET_DATA_ROOT)
        rec["source"] = data.get("source")
        rec["symbol"] = data.get("symbol")
        if rec["source"] != "gateio_public_spot" or rec["symbol"] != "BTC_USDT":
            raise ValueError("UNEXPECTED_SOURCE_OR_SYMBOL")

        frames = dict(data.get("timeframes") or {})
        # Reuse the existing fail-closed canonical reader; 1m remains a precision
        # input and is not added to the 15m setup-generation timeframe set.
        frames["1m"] = read_closed_candles("1m", root=MARKET_DATA_ROOT, min_bars=200)
        details = {}
        for timeframe, period in TIMEFRAME_SECONDS.items():
            rows = frames.get(timeframe, [])
            if not rows:
                raise ValueError("NO_BARS_" + timeframe)
            row = rows[-1]
            close_time = int(row["close_time"])
            age = int(time.time() - close_time)
            close = float(row["close"])
            if not math.isfinite(close) or close <= 0:
                raise ValueError("INVALID_CLOSE_" + timeframe)
            if age < 0 or age > MAX_AGE_SECONDS[timeframe]:
                raise ValueError(
                    "STALE_OR_FUTURE_CANDLE_" + timeframe + ":age=" + str(age)
                )
            details[timeframe] = {
                "bars": len(rows),
                "last_close_time": close_time,
                "age_seconds": age,
                "close": close,
            }
        rec["timeframes"] = details

        states = {}
        for service in SERVICES:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            states[service] = result.stdout.strip() if result.returncode == 0 else "INACTIVE"
        rec["services"] = states
        if not all(value == "active" for value in states.values()):
            raise ValueError("SERVICE_NOT_ACTIVE")
        rec["ok"] = True
    except Exception as exc:
        rec["ok"] = False
        rec["error"] = type(exc).__name__ + ":" + str(exc)[:300]
    return rec


def main() -> int:
    release = release_provenance()
    run_id = uuid.uuid4().hex
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = (LOG.parent / ".gateio_feed_soak_v2.lock").open("a", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({
            "schema": "hes_gateio_soak_error_v1",
            "error": "SOAK_ALREADY_RUNNING",
            "ok": False,
            "execution_enabled": False,
            "orders_placed": False,
        }), flush=True)
        return 4

    start = time.monotonic()
    deadline = start + DURATION
    sequence = 0
    while True:
        sequence += 1
        record = sample(sequence, start, run_id, release)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps(record, sort_keys=True), flush=True)
        if not record["ok"]:
            return 2
        if os.environ.get("HES_SOAK_ONCE") == "1":
            return 0
        if time.monotonic() >= deadline:
            break
        time.sleep(min(INTERVAL, max(0, deadline - time.monotonic())))

    elapsed = int(time.monotonic() - start)
    summary = {
        "schema": "hes_gateio_soak_summary_v3",
        "run_id": run_id,
        **release,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "samples": sequence,
        "duration_seconds": elapsed,
        "timeframes": list(TIMEFRAME_SECONDS),
        "services": list(SERVICES),
        "passed": sequence >= 1400 and elapsed >= DURATION,
        "execution_enabled": False,
        "orders_placed": False,
    }
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if summary["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
