"""Verify the immutable raw snapshot used by the 1,049-observation OOS audit.

This is an integrity gate only. It does not run strategy logic or promote results.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/trades.csv")
    parser.add_argument(
        "--manifest",
        default="docs/backtest/oos_snapshot_1049_v1.json",
    )
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    data = Path(args.csv).read_bytes()

    actual_sha = git_blob_sha1(data)
    expected_sha = manifest["source_blob_sha1"]
    if actual_sha != expected_sha:
        raise AssertionError(
            f"snapshot blob mismatch: expected {expected_sha}, got {actual_sha}"
        )

    with Path(args.csv).open("r", encoding="utf-8", newline="") as handle:
        rows = sum(1 for _ in csv.DictReader(handle))

    expected_rows = manifest["raw_snapshot_observed"]["rows"]
    if rows != expected_rows:
        raise AssertionError(
            f"snapshot row-count mismatch: expected {expected_rows}, got {rows}"
        )

    expected_bytes = manifest["raw_snapshot_observed"]["bytes"]
    if len(data) != expected_bytes:
        raise AssertionError(
            f"snapshot byte-size mismatch: expected {expected_bytes}, got {len(data)}"
        )

    print(
        json.dumps(
            {
                "snapshot_id": manifest["snapshot_id"],
                "blob_sha1": actual_sha,
                "rows": rows,
                "bytes": len(data),
                "integrity": "PASS",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
