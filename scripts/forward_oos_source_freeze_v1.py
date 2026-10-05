#!/usr/bin/env python3
import csv
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

BOUNDARY = datetime.fromisoformat("2026-10-05T00:00:00+00:00")
SOURCE_COMMIT = "f396de84cb7f4c6b16e81effc91b653e26049ab4"
SOURCE_PATH = "data/trades.csv"

raw = subprocess.check_output(
    ["git", "show", f"{SOURCE_COMMIT}:{SOURCE_PATH}"],
)
rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
eligible = []
for r in rows:
    ts = datetime.fromisoformat(r["updated"].replace("Z", "+00:00"))
    if ts > BOUNDARY:
        eligible.append((ts, r))

times = [x[0] for x in eligible]
seqs = [int(x[1]["sequence"]) for x in eligible]
strict_ts = all(a < b for a, b in zip(times, times[1:]))
unique_seq = len(seqs) == len(set(seqs))
strict_seq = all(a < b for a, b in zip(seqs, seqs[1:]))

manifest = {
    "status": "FROZEN",
    "source_commit": SOURCE_COMMIT,
    "source_path": SOURCE_PATH,
    "source_sha256": hashlib.sha256(raw).hexdigest(),
    "boundary_timestamp": "2026-10-05T00:00:00+00:00",
    "eligibility": "updated timestamp strictly greater than boundary",
    "source_rows_total": len(rows),
    "forward_rows": len(eligible),
    "first_eligible_timestamp": times[0].isoformat().replace("+00:00", "Z") if times else None,
    "last_eligible_timestamp": times[-1].isoformat().replace("+00:00", "Z") if times else None,
    "timestamp_strictly_increasing": strict_ts,
    "sequence_unique": unique_seq,
    "sequence_strictly_increasing": strict_seq,
    "outcomes_inspected": False,
    "protocol_mutation": False,
    "winner_reselection": False,
    "promotion": "BLOCKED",
    "live_execution": False,
}
assert manifest["source_sha256"]
assert strict_ts and unique_seq and strict_seq
Path("forward_oos_source_freeze_v1.json").write_text(
    json.dumps(manifest, indent=2) + "\n"
)
print("FORWARD_OOS_SOURCE_FREEZE_VALID")
print(json.dumps(manifest, indent=2))
