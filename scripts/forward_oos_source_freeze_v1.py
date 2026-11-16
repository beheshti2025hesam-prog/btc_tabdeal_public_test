#!/usr/bin/env python3
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
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
timestamp_nondecreasing = all(a <= b for a, b in zip(times, times[1:]))
timestamp_groups = defaultdict(set)
for ts, row in eligible:
    timestamp_groups[ts].add(row["price"])
ambiguous_equal_timestamp_count = sum(
    1 for prices in timestamp_groups.values() if len(prices) > 1
)
sequence_values_present = sum(1 for _, row in eligible if row.get("sequence") not in (None, ""))

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
    "event_timestamp_nondecreasing_in_source_file": timestamp_nondecreasing,
    "ambiguous_equal_timestamp_price_groups": ambiguous_equal_timestamp_count,
    "sequence_metadata_values_present": sequence_values_present,
    "sequence_semantics": "OPAQUE_INFORMATIONAL_METADATA_NOT_ANALYZED",
    "sequence_used_for_identity_ordering_or_gap_detection": False,
    "outcomes_inspected": False,
    "protocol_mutation": False,
    "winner_reselection": False,
    "promotion": "BLOCKED",
    "live_execution": False,
}
assert manifest["source_sha256"]
assert timestamp_nondecreasing and ambiguous_equal_timestamp_count == 0
Path("forward_oos_source_freeze_v1.json").write_text(
    json.dumps(manifest, indent=2) + "\n"
)
print("FORWARD_OOS_SOURCE_FREEZE_VALID")
print(json.dumps(manifest, indent=2))
