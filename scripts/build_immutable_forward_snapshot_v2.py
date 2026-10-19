#!/usr/bin/env python3
"""Build a fail-closed immutable forward snapshot candidate.

Identity/capacity only. Never inspects strategy outcomes.
"""
from __future__ import annotations
import csv, hashlib, json, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.backtest.real_data import RealDataBacktest

SOURCE_PATH = "data/trades.csv"
BOUNDARY = datetime.fromisoformat("2026-10-05T00:00:00+00:00")
REQUIRED = 3600

def main():
    commit = subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip()
    raw = subprocess.check_output(["git","show",f"{commit}:{SOURCE_PATH}"])
    sha = hashlib.sha256(raw).hexdigest()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(raw); path=f.name
    try:
        bt=RealDataBacktest(csv_path=path)
        full=bt.run()
        obs=list(bt._last_observations)
    finally:
        Path(path).unlink(missing_ok=True)

    # Preserve pipeline semantics: observations come from the real HES parser,
    # not raw trade rows or ad-hoc minute bucketing.
    forward=[o for o in obs if o.timestamp > BOUNDARY]
    original_ts=[o.timestamp for o in forward]
    strict_source_order=all(a < b for a,b in zip(original_ts, original_ts[1:]))
    timestamps=sorted(original_ts)
    strict_sorted=all(a < b for a,b in zip(timestamps,timestamps[1:]))
    unique=len(set(timestamps))==len(timestamps)
    ready=(len(forward)>=REQUIRED and strict_source_order and strict_sorted and unique)

    result={
      "artifact":"immutable_forward_snapshot_candidate_v2",
      "status":"READY_FOR_IMMUTABLE_SOURCE_LOCK" if ready else "IMMUTABLE_CANDIDATE_ACCUMULATING",
      "source_commit":commit,"source_path":SOURCE_PATH,"source_sha256":sha,
      "boundary_timestamp":BOUNDARY.isoformat(),
      "source_rows_total":full.rows_read,"source_valid_rows":full.rows_valid,
      "full_observations":full.observations,
      "forward_observations":len(forward),
      "required_one_minute_observations":REQUIRED,
      "forward_timestamp_strictly_increasing_in_source":strict_source_order,
      "forward_timestamp_strictly_increasing_after_sort":strict_sorted,
      "forward_timestamp_unique":unique,
      "outcomes_inspected":False,
      "threshold_tuned":False,"winner_reselected":False,
      "records_deleted":False,"protocol_mutation":False,
      "live_execution":False,"promotion":"BLOCKED",
      "verdict":("CAPACITY_REACHED_PENDING_INDEPENDENT_VALIDATION"
                 if ready else "ACCUMULATING_INSUFFICIENT_VALID_ONE_MINUTE_OBSERVATIONS"),
    }
    Path("immutable_forward_snapshot_candidate_v2.json").write_text(
      json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
