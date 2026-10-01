#!/usr/bin/env python3
"""Candidate C v1 deterministic, research-only evaluator.

This evaluator is intentionally self-contained and binds to the frozen Candidate C
definition and snapshot lineage. It does not import or retarget Rule A evaluators.
"""
import csv, json, hashlib, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
DEF=ROOT/"evidence/candidate_c_definition_v1.json"
SNAP=ROOT/"evidence/candidate_c_fresh_snapshot_20261001.json"
OUT=ROOT/"evidence/candidate_c_evaluator_contract_20261001.json"

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    d=json.loads(DEF.read_text())
    s=json.loads(SNAP.read_text())
    assert d["candidate_id"]=="CANDIDATE_RESEARCH_INDEPENDENT_C"
    assert d["candidate_version"]=="C-v1"
    assert s["candidate_id"]==d["candidate_id"]
    assert s["active_blob"]=="eef65102d4671a43f11f9dc311e0617aa220eb64"
    assert s["integrity"]["verified_archive_count"]==12
    assert d["evaluation"]["folds"]==8
    assert d["evaluation"]["train_bars"]==800
    assert d["evaluation"]["test_bars"]==400
    assert d["evaluation"]["step_bars"]==400
    contract={
      "artifact_id":"CANDIDATE_C_EVALUATOR_CONTRACT_2026-10-01",
      "status":"BINDING_VERIFIED_NO_OOS_STARTED",
      "definition_sha256":sha256_file(DEF),
      "snapshot_file_sha256":sha256_file(SNAP),
      "active_blob":s["active_blob"],
      "algorithm":{
        "features":["ema20","ema50","atr14","prior_20_bar_high","prior_20_bar_low"],
        "long":"close_t > prior_20_bar_high AND ema20_t > ema50_t",
        "short":"close_t < prior_20_bar_low AND ema20_t < ema50_t",
        "entry":"next_bar_open",
        "stop_atr":1.5,"target_atr":2.0,"max_holding_bars":30,
        "max_concurrent_positions":1,"opposite_signal_while_open":"ignored",
        "walk_forward":{"folds":8,"train_bars":800,"test_bars":400,"step_bars":400},
        "timestamp_embargo":True
      },
      "independence":{
        "rule_a_evaluator_imported":False,
        "rule_a_results_reused":False,
        "candidate_b_logic_reused":False,
        "post_result_tuning":False
      },
      "safety":{"research_only":True,"live_execution":False,"wallet_operations":False,"promotion":False,
                "data_engine_v1_merge_rebase_sync":False},
      "oos_run_started":False,
      "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    OUT.write_text(json.dumps(contract,indent=2)+"
")
    print(json.dumps(contract,indent=2))
if __name__=="__main__": main()
