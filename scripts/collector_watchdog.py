#!/usr/bin/env python3
"""Fail-fast health check for persistent Tabdeal raw-data acquisition."""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data" / "trades.csv"
STATE = ROOT / "data" / "runtime" / "supervisor_state.json"
MAX_TRADE_AGE = int(os.getenv("HES_MAX_TRADE_AGE_SECONDS", "180"))


def fail(message: str) -> int:
    print(f"WATCHDOG FAIL: {message}", flush=True)
    return 1


def main() -> int:
    if not TRADES.exists():
        return fail(f"missing {TRADES}")

    try:
        with TRADES.open("r", newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(handle)
            last = None
            for row in rows:
                last = row
    except Exception as exc:
        return fail(f"cannot read trades.csv: {exc}")

    if not last:
        return fail("trades.csv has no data rows")

    updated = last.get("updated")
    sequence = last.get("sequence")
    if not updated or not sequence:
        return fail("latest row is missing updated or sequence")

    try:
        timestamp = datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except ValueError as exc:
        return fail(f"invalid latest trade timestamp {updated!r}: {exc}")

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    age = time.time() - timestamp.timestamp()
    if age > MAX_TRADE_AGE:
        return fail(
            f"latest trade is {age:.1f}s old; threshold={MAX_TRADE_AGE}s; sequence={sequence}"
        )

    state = None
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            state = None

    print(
        f"WATCHDOG OK: trade_age={age:.1f}s sequence={sequence} "
        f"supervisor_event={state.get('event') if state else 'unknown'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
