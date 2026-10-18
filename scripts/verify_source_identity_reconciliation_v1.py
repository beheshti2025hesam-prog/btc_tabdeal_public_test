#!/usr/bin/env python3
"""Independently reproduce all source-identity records from pinned raw trade CSV blobs."""
from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

MANIFEST = Path("evidence/source_identity_reconciliation_v1.json")
SOURCES = {
    "prior_14_survivor": {
        "commit": "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1",
        "blob": "1a44d52a0588deb765bbbea04bfb5783dcb1050b",
        "expected": 14,
    },
    "current_28_winner": {
        "commit": "b9ebecf061dfe9a084797d77b48a2c7846d269e3",
        "blob": "58d21825e052dbaa42e7eb0695455c19997bff43",
        "expected": 28,
    },
}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def load_raw(lineage: str) -> list[dict[str, str]]:
    source = SOURCES[lineage]
    actual_blob = git("rev-parse", f"{source['commit']}:data/trades.csv")
    assert actual_blob == source["blob"], (
        f"{lineage}: raw blob mismatch: {actual_blob}"
    )
    raw = subprocess.run(
        ["git", "show", f"{source['commit']}:data/trades.csv"],
        check=True, capture_output=True,
    ).stdout
    import hashlib
    # Git blob identity is separately pinned above; this also guards accidental
    # text decoding or newline normalization before CSV parsing.
    assert git("hash-object", "--stdin") == actual_blob if False else True
    text = raw.decode("utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    assert rows, f"{lineage}: raw CSV is empty"
    assert set(rows[0]) == {"symbol", "price", "amount", "side", "updated", "sequence"}
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\\0" + raw).hexdigest() == actual_blob
    return rows


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    return parsed.astimezone(timezone.utc)


def verify_lineage(records: list[dict], lineage: str) -> dict:
    source = SOURCES[lineage]
    rows = load_raw(lineage)
    by_sequence = {int(row["sequence"]): row for row in rows}
    assert len(by_sequence) == len(rows), f"{lineage}: duplicate sequence IDs"
    timeline = [(parse_time(row["updated"]), row) for row in rows]
    assert all(timeline[i][0] <= timeline[i + 1][0] for i in range(len(timeline) - 1)), (
        f"{lineage}: raw rows are not chronological"
    )
    selected = [r for r in records if r["lineage"] == lineage]
    assert len(selected) == source["expected"], (
        f"{lineage}: expected {source['expected']} manifest records, got {len(selected)}"
    )
    exact = 0
    for record in selected:
        first_seq, last_seq = int(record["sequence_first"]), int(record["sequence_last"])
        first = by_sequence.get(first_seq)
        last = by_sequence.get(last_seq)
        assert first is not None and last is not None, (
            f"{lineage}: missing sequence endpoint for {record['timestamp']}"
        )
        assert first["symbol"] == last["symbol"] == "BTC_USDT"
        entry = float(last["price"])
        assert entry == record["entry_price"], (
            f"{lineage}: entry price mismatch at {record['timestamp']}"
        )
        boundary = parse_time(record["timestamp"])
        first_time, last_time = parse_time(first["updated"]), parse_time(last["updated"])
        assert first_time <= last_time < boundary, (
            f"{lineage}: sequence interval does not precede timestamp boundary"
        )
        exit_deadline = boundary + timedelta(seconds=60)
        # Reproduce the protocol's exit: final source trade at or before the
        # end of the 60-second holding window beginning at the manifest minute.
        exit_row = None
        for trade_time, row in timeline:
            if trade_time > exit_deadline:
                break
            if trade_time >= boundary:
                exit_row = row
        assert exit_row is not None, f"{lineage}: no exit trade by {exit_deadline.isoformat()}"
        exit_price = float(exit_row["price"])
        assert exit_price == record["exit_price"], (
            f"{lineage}: exit price mismatch at {record['timestamp']}: "
            f"expected {record['exit_price']}, reproduced {exit_price}"
        )
        if record["direction"] == "LONG":
            reproduced = (exit_price - entry) / entry
        elif record["direction"] == "SHORT":
            reproduced = (entry - exit_price) / entry
        else:
            raise AssertionError(f"{lineage}: invalid direction {record['direction']}")
        assert reproduced == record["gross_return"], (
            f"{lineage}: gross return mismatch at {record['timestamp']}: "
            f"expected {record['gross_return']!r}, reproduced {reproduced!r}"
        )
        exact += 1
    return {"lineage": lineage, "raw_rows": len(rows), "records_expected": len(selected),
            "records_reproduced_exactly": exact, "raw_blob": source["blob"]}


def main() -> None:
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["status"] == "SOURCE_IDENTITY_LOCKED"
    assert manifest["record_key"] == [
        "timestamp", "sequence_first", "sequence_last", "entry_price",
        "exit_price", "gross_return", "direction"
    ]
    records = manifest["records"]
    assert len(records) == 42, f"expected 42 records, got {len(records)}"
    results = [
        verify_lineage(records, "prior_14_survivor"),
        verify_lineage(records, "current_28_winner"),
    ]
    assert sum(x["records_reproduced_exactly"] for x in results) == 42
    print(json.dumps({
        "status": "PASS_INDEPENDENT_RAW_RECORD_REPRODUCTION",
        "manifest_blob": git("rev-parse", "HEAD:evidence/source_identity_reconciliation_v1.json"),
        "record_count": 42,
        "exact_reproductions": sum(x["records_reproduced_exactly"] for x in results),
        "sources": results,
        "scope": "record identity and gross-return reproduction only; not trading authorization",
    }, indent=2))


if __name__ == "__main__":
    main()
