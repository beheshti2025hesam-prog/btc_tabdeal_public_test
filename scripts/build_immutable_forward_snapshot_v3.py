#!/usr/bin/env python3
"""Build a fail-closed forward snapshot candidate from the real HES pipeline.

This artifact performs identity/integrity/capacity checks only. It never
evaluates outcomes and never mutates the locked historical protocol.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.data_engine.normalizer import RawDataNormalizer

SOURCE_PATH="data/trades.csv"
BOUNDARY=datetime.fromisoformat("2026-10-05T00:00:00+00:00")
REQUIRED=3600
WRITER_PROVENANCE_PATH="archive/run196_reconciliation_closure.json"
N_PLUS_1_WRITER_OBSERVATION_PATH="archive/n_plus_1_writer_attribution_observation_v1.json"

def main():
    commit=os.environ.get("SOURCE_COMMIT","").strip()
    if not commit:
        raise RuntimeError("SOURCE_COMMIT is required; moving HEAD is not an immutable source pin.")
    try:
        subprocess.check_call(["git","cat-file","-e",f"{commit}^{commit}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.check_call(["git","cat-file","-e",f"{commit}:{SOURCE_PATH}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Immutable source commit/path unavailable: {commit}:{SOURCE_PATH}") from exc
    raw=subprocess.check_output(["git","show",f"{commit}:{SOURCE_PATH}"])
    sha=hashlib.sha256(raw).hexdigest()

    # Provenance guard: the historical closure artifact is the durable source
    # for the retired-writer handoff. It does NOT prove that the current/future
    # forward rows have one writer, so this builder remains fail-closed until
    # a durable N+1 writer-attribution artifact exists for the snapshot source.
    provenance_exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{WRITER_PROVENANCE_PATH}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    with tempfile.NamedTemporaryFile(suffix=".csv",delete=False) as f:
        f.write(raw); path=f.name
    try:
        # Raw-source integrity: validate the actual source order before any
        # pipeline sorting can occur.
        reader=RawDataReader(active_file=path,archive_dir="__no_archive__")
        validator=RawDataValidator(); normalizer=RawDataNormalizer()
        raw_rows=list(reader.read_all())
        valid_trades=[]; invalid=0
        for row in raw_rows:
            errors=validator.validate_row(row)
            if errors: invalid+=1
            else: valid_trades.append(normalizer.normalize_row(row))

        source_ts=[t.timestamp for t in valid_trades]
        source_seq=[t.sequence for t in valid_trades]
        source_ts_order=all(a<b for a,b in zip(source_ts,source_ts[1:]))
        source_seq_order=all(a<b for a,b in zip(source_seq,source_seq[1:]))
        ts_unique=len(set(source_ts))==len(source_ts)
        seq_unique=len(set(source_seq))==len(source_seq)

        # Identity-only one-minute observation extraction. Deliberately does
        # not invoke RealDataBacktest, strategy, risk, features, or realized
        # next-candle outcomes. An observation is the end of an eligible
        # continuous one-minute candle after the locked EMA warm-up boundary.
        candles=TradeCandleAggregator(60).aggregate(valid_trades)
        observations=[]
        continuity_excluded=0
        for index in range(20 - 1, len(candles) - 1):
            candle=candles[index]
            next_candle=candles[index + 1]
            if candle.symbol != next_candle.symbol:
                continue
            if next_candle.start != candle.end:
                continuity_excluded += 1
                continue
            observations.append(candle.end)
    finally:
        Path(path).unlink(missing_ok=True)

    forward=[t for t in observations if t>BOUNDARY]
    ts=forward
    strict_obs=all(a<b for a,b in zip(ts,ts[1:]))
    obs_unique=len(set(ts))==len(ts)
    n1_writer_observation_exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{N_PLUS_1_WRITER_OBSERVATION_PATH}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    # The real pipeline reports continuity exclusions, but the historical
    # lock requires an explicit gap/continuity check and durable single-writer
    # lineage before an immutable forward lock. Presence of the Run #196
    # closure is only a predecessor/handoff proof, never a substitute for
    # current N+1 writer attribution.
    continuity_ok = continuity_excluded == 0
    single_writer_lineage_verified = False
    ready=(len(forward)>=REQUIRED and source_ts_order and source_seq_order
           and ts_unique and seq_unique and strict_obs and obs_unique
           and invalid==0 and continuity_ok and provenance_exists
           and single_writer_lineage_verified)

    result={
      "artifact":"immutable_forward_snapshot_candidate_v3",
      "status":"READY_FOR_INDEPENDENT_IMMUTABLE_LOCK_VALIDATION" if ready else "IMMUTABLE_CANDIDATE_ACCUMULATING",
      "source_commit":commit,"source_path":SOURCE_PATH,"source_sha256":sha,
      "boundary_timestamp":BOUNDARY.isoformat(),
      "source_rows_total":len(raw_rows),"source_valid_rows":len(valid_trades),"source_invalid_rows":invalid,
      "full_observations":len(observations),"forward_observations":len(forward),
      "required_one_minute_observations":REQUIRED,
      "source_timestamp_strictly_increasing":source_ts_order,
      "source_sequence_strictly_increasing":source_seq_order,
      "source_timestamp_unique":ts_unique,"source_sequence_unique":seq_unique,
      "forward_observation_timestamp_strictly_increasing":strict_obs,
      "forward_observation_timestamp_unique":obs_unique,
      "continuity_excluded":continuity_excluded,
      "continuity_policy":"FAIL_CLOSED_REQUIRES_ZERO_EXCLUDED_BOUNDARIES",
      "continuity_check_passed":continuity_ok,
      "writer_provenance_artifact":WRITER_PROVENANCE_PATH,
      "writer_provenance_artifact_present":provenance_exists,
      "n_plus_1_writer_observation_artifact":N_PLUS_1_WRITER_OBSERVATION_PATH,
      "n_plus_1_writer_observation_artifact_present":n1_writer_observation_exists,
      "single_writer_lineage_verified":single_writer_lineage_verified,
      "single_writer_lineage_status":"BLOCKED_PENDING_DURABLE_N_PLUS_1_ATTRIBUTION",
      "outcomes_inspected":False,"outcome_pipeline_invoked":False,"strategy_evaluated":False,"risk_evaluated":False,"threshold_tuned":False,"winner_reselected":False,
      "records_deleted":False,"protocol_mutation":False,"live_execution":False,
      "promotion":"BLOCKED",
      "verdict":"CAPACITY_REACHED_PENDING_INDEPENDENT_VALIDATION" if ready else "ACCUMULATING_OR_INTEGRITY_OR_PROVENANCE_BLOCKED"
    }
    Path("immutable_forward_snapshot_candidate_v3.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
