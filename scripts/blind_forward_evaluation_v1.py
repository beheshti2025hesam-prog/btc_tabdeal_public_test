#!/usr/bin/env python3
"""Blind Forward OOS Evaluation v1.

Research-only, fail-closed. Uses the immutable Run #196 source object and the
already locked 800/400/400, 8-fold, >14bps protocol. No tuning, reselection,
deletion, protocol mutation, or live execution.
"""
from __future__ import annotations
import csv, hashlib, json, subprocess, tempfile, sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repository-root imports work when invoked directly by GitHub Actions.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.real_data import RealDataBacktest

SOURCE_COMMIT="f396de84cb7f4c6b16e81effc91b653e26049ab4"
SOURCE_PATH="data/trades.csv"
BOUNDARY=datetime.fromisoformat("2026-10-05T00:00:00+00:00")
TRAIN,TEST,STEP,FOLDS=800,400,400,8
THRESHOLD=0.0014
EXPECTED_SOURCE_SHA="c5dbd78fe8aade258c28f1254f0a399051ab32d3b026e246ff36285dd020de87"

def main():
    raw=subprocess.check_output(["git","show",f"{SOURCE_COMMIT}:{SOURCE_PATH}"])
    source_sha=hashlib.sha256(raw).hexdigest()
    assert source_sha==EXPECTED_SOURCE_SHA,(source_sha,EXPECTED_SOURCE_SHA)

    with tempfile.NamedTemporaryFile(suffix=".csv",delete=False) as f:
        f.write(raw); csv_path=f.name

    try:
        bt=RealDataBacktest(csv_path=csv_path)
        full=bt.run()
        observations=list(bt._last_observations)
        forward=[o for o in observations if o.timestamp > BOUNDARY]
        forward.sort(key=lambda o:o.timestamp)
        timestamps=[o.timestamp for o in forward]
        strict_ts=all(a<b for a,b in zip(timestamps,timestamps[1:]))

        # The locked protocol requires 8 folds of 800 train + 400 test.
        required=TRAIN+TEST+(FOLDS-1)*STEP
        protocol_ready=len(forward)>=required

        result={
          "status":"BLIND_FORWARD_EVALUATION",
          "source_commit":SOURCE_COMMIT,
          "source_path":SOURCE_PATH,
          "source_sha256":source_sha,
          "boundary_timestamp":"2026-10-05T00:00:00+00:00",
          "eligibility":"observation timestamp strictly greater than boundary",
          "source_rows_total":full.rows_read,
          "source_valid_rows":full.rows_valid,
          "full_observations":full.observations,
          "forward_observations":len(forward),
          "required_observations_for_8_locked_folds":required,
          "protocol_ready_for_8_folds":protocol_ready,
          "first_forward_observation":timestamps[0].isoformat().replace("+00:00","Z") if timestamps else None,
          "last_forward_observation":timestamps[-1].isoformat().replace("+00:00","Z") if timestamps else None,
          "forward_timestamp_strictly_increasing":strict_ts,
          "protocol":{"train":TRAIN,"test":TEST,"step":STEP,"folds":FOLDS,"gross_threshold_bps":14},
          "outcomes_inspected":False if not protocol_ready else True,
          "threshold_tuned":False,
          "winner_reselected":False,
          "records_deleted":False,
          "protocol_mutation":False,
          "live_execution":False,
          "promotion":"BLOCKED",
          "verdict":(
            "G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS"
            if not protocol_ready else "READY_FOR_LOCKED_FORWARD_EVALUATION"
          ),
          "claim_boundary":{
            "predictive_validity":False,"causality":False,
            "market_generalization":False
          }
        }
        Path("blind_forward_evaluation_v1.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result,indent=2))
    finally:
        Path(csv_path).unlink(missing_ok=True)

if __name__=="__main__":
    main()
