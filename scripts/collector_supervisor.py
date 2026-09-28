#!/usr/bin/env python3
"""Continuously supervise the HES Trade Agent Tabdeal collector."""

from __future__ import annotations
import json
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "tabdeal_futures_ws_test.py"
STATE_DIR = ROOT / "data" / "runtime"
STATE_FILE = STATE_DIR / "supervisor_state.json"
RESTART_DELAY_SECONDS = int(os.getenv("HES_COLLECTOR_RESTART_DELAY", "5"))

stopping = False
child: subprocess.Popen[str] | None = None

def write_state(event: str, **extra: object) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "HES Trade Agent",
        "owner": "Seyed Hesameddin Beheshti Shirazi",
        "collector": "Tabdeal BTC_USDT",
        "event": event,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **extra,
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, STATE_FILE)

def stop(signum: int, _frame: object) -> None:
    global stopping
    stopping = True
    write_state("stop_requested", signal=signum)
    if child is not None and child.poll() is None:
        child.terminate()

def main() -> int:
    global child
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if not COLLECTOR.exists():
        raise FileNotFoundError(COLLECTOR)

    while not stopping:
        started = time.time()
        write_state("starting", pid=os.getpid())

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["HES_COLLECTOR_MODE"] = "persistent-vps"
        env["HES_COLLECTOR_GIT_CHECKPOINT"] = "0"
        env.pop("COLLECTOR_RUN_SECONDS", None)

        child = subprocess.Popen(
            [os.environ.get("PYTHON", "python3"), str(COLLECTOR)],
            cwd=ROOT,
            env=env,
            text=True,
        )
        write_state("collector_started", child_pid=child.pid)

        return_code = child.wait()
        uptime_seconds = round(time.time() - started, 3)
        write_state(
            "collector_exited",
            child_pid=child.pid,
            return_code=return_code,
            uptime_seconds=uptime_seconds,
        )
        child = None

        if stopping:
            break
        time.sleep(RESTART_DELAY_SECONDS)

    write_state("supervisor_stopped")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
