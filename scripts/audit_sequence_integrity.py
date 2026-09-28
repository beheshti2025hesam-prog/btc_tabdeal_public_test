#!/usr/bin/env python3
"""Audit global sequence ordering across active CSV and archived CSV files."""

from __future__ import annotations

import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "data" / "trades.csv"
ARCHIVE = ROOT / "data" / "archive"


def sequences(path: Path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("sequence")
            if raw is None or raw == "":
                continue
            yield int(raw)


def main() -> int:
    files = []
    if ACTIVE.exists():
        files.append(ACTIVE)
    if ARCHIVE.exists():
        files.extend(
            sorted(
                p for p in ARCHIVE.iterdir()
                if p.suffix.lower() == ".csv"
            )
        )

    previous = None
    count = 0

    for path in files:
        local_previous = None
        for sequence in sequences(path):
            if local_previous is not None and sequence <= local_previous:
                print(
                    f"FAIL: non-increasing sequence inside {path}: "
                    f"{local_previous} -> {sequence}"
                )
                return 1

            if previous is not None and sequence <= previous:
                print(
                    f"FAIL: global sequence overlap/order violation at {path}: "
                    f"{previous} -> {sequence}"
                )
                return 1

            local_previous = sequence
            previous = sequence
            count += 1

    if count == 0:
        print("FAIL: no valid sequence rows found")
        return 1

    print(f"OK: {count} sequence rows; global_max={previous}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
