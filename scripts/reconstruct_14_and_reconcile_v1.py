#!/usr/bin/env python3
import csv, hashlib, json, os, sys
from pathlib import Path
from collections import defaultdict

THRESHOLD = 0.0014

def run_lineage(source_root, csv_path, raw_blob_sha, lineage_name):
    sys.path.insert(0, str(Path(source_root).resolve()))
    from core.backtest.real_data import RealDataBacktest
    from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
    from core.backtest.costs import BacktestCostModel, CostScenario
    from core.backtest.oos_cost_matrix import evaluate_oos_cost_matrix

    runner = RealDataBacktest(str(csv_path))
    wf = runner.run_walk_forward(
        train_size=REAL_BTC_USDT_OOS_V1.train_size,
        test_size=REAL_BTC_USDT_OOS_V1.test_size,
        step_size=REAL_BTC_USDT_OOS_V1.step_size,
        embargo_size=REAL_BTC_USDT_OOS_V1.embargo_size,
        max_folds=REAL_BTC_USDT_OOS_V1.expected_fold_count,
    )
    assert len(wf.folds) == 8

    # Re-read raw trades to recover exact entry/exit sequence ranges.
    from core.data_engine.reader import RawDataReader
    from core.data_engine.validator import RawDataValidator
    from core.data_engine.normalizer import RawDataNormalizer
    reader = RawDataReader(active_file=str(csv_path), archive_dir="__no_archive__")
    validator = RawDataValidator()
    normalizer = RawDataNormalizer()
    trades=[]
    for row in reader.read_all():
        assert not validator.validate_row(row)
        trades.append(normalizer.normalize_row(row))
    trades.sort(key=lambda t:(t.timestamp,t.sequence or -1))

    seq_by_minute=defaultdict(list)
    for t in trades:
        epoch=int(t.timestamp.timestamp())
        bucket=epoch-(epoch%60)
        seq_by_minute[(t.symbol,bucket)].append(t.sequence)

    model = BacktestCostModel(transaction_cost_bps_per_side=5.0, slippage_bps_per_side=2.0)
    rows=[]
    for fold in wf.folds:
        for j, sample in enumerate(fold.test_samples):
            gross=model.gross_return(sample) if sample.decision.value in ("LONG","SHORT") else None
            net14=(gross-0.0014) if gross is not None else None
            epoch=int(sample.timestamp.timestamp())
            seqs=seq_by_minute.get(("BTC_USDT",epoch-(epoch%60)),[])
            # Deterministic identity: lineage + exact record fields.
            identity_payload={
                "raw_blob_sha":raw_blob_sha,
                "fold":fold.index,
                "test_index":j,
                "timestamp":sample.timestamp.isoformat(),
                "entry_price":sample.entry_price,
                "exit_price":sample.exit_price,
                "decision":sample.decision.value,
                "sequence_first":min(seqs) if seqs else None,
                "sequence_last":max(seqs) if seqs else None,
            }
            oid=hashlib.sha256(json.dumps(identity_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            rows.append({
                "observation_id":oid,
                "lineage":lineage_name,
                "raw_blob_sha":raw_blob_sha,
                "fold":fold.index,
                "test_index":j,
                "timestamp":sample.timestamp.isoformat(),
                "sequence_first":min(seqs) if seqs else None,
                "sequence_last":max(seqs) if seqs else None,
                "entry_price":sample.entry_price,
                "exit_price":sample.exit_price,
                "direction":sample.decision.value,
                "gross_outcome":gross,
                "net_14bps":net14,
                "classification_14bps":(
                    "Winner" if gross is not None and gross > THRESHOLD else
                    "Control" if gross is not None else "NotEvaluated"
                ),
                "risk":sample.risk.value,
                "cost_model":"5bps fee + 2bps slippage per side",
            })
    evaluated=[r for r in rows if r["gross_outcome"] is not None]
    assert len(evaluated)==wf.evaluated, (len(evaluated),wf.evaluated)
    winners=[r for r in evaluated if r["classification_14bps"]=="Winner"]
    controls=[r for r in evaluated if r["classification_14bps"]=="Control"]
    # Exact old cost-matrix survivor count must be 14 for old lineage.
    if lineage_name=="prior_1049":
        assert len(evaluated)==1049, len(evaluated)
        assert len(winners)==14, len(winners)
    if lineage_name=="current_1027":
        assert len(evaluated)==1027, len(evaluated)
        assert len(winners)==28, len(winners)
        assert len(controls)==999, len(controls)
    return {
        "lineage":lineage_name,
        "raw_blob_sha":raw_blob_sha,
        "protocol":{"train":800,"test":400,"step":400,"folds":8,"threshold_bps_gross":14},
        "counts":{"evaluated":len(evaluated),"winners_gt_14bps":len(winners),"controls_le_14bps":len(controls)},
        "rows":rows,
        "survivors_14bps":winners,
    }

def exact_key(r):
    return (
        r["timestamp"], r["sequence_first"], r["sequence_last"],
        r["entry_price"], r["exit_price"], r["direction"], r["gross_outcome"]
    )

def reconcile(old, cur):
    old_survivors=old["survivors_14bps"]
    cur_winners=[r for r in cur["rows"] if r["classification_14bps"]=="Winner"]
    old_map=defaultdict(list)
    for r in old_survivors:
        old_map[exact_key(r)].append(r)
    matrix=[]
    matched_old=set()
    for c in cur_winners:
        matches=old_map.get(exact_key(c),[])
        for m in matches: matched_old.add(m["observation_id"])
        matrix.append({
            "current_observation_id":c["observation_id"],
            "current_fold":c["fold"],
            "current_timestamp":c["timestamp"],
            "current_sequence_first":c["sequence_first"],
            "current_sequence_last":c["sequence_last"],
            "current_entry_price":c["entry_price"],
            "current_exit_price":c["exit_price"],
            "current_gross_outcome":c["gross_outcome"],
            "current_14bps_classification":c["classification_14bps"],
            "current_Winner_or_Control":"Winner",
            "prior_14_survivor": bool(matches),
            "prior_observation_ids":[m["observation_id"] for m in matches],
            "exact_match": bool(matches),
            "match_count":len(matches),
            "lineage":"current_1027 vs prior_1049",
        })
    unmatched_old=[r for r in old_survivors if r["observation_id"] not in matched_old]
    return {
        "protocol":{"exact_record_match_key":["timestamp","sequence_first","sequence_last","entry_price","exit_price","direction","gross_outcome"],
                    "threshold_bps":14,"no_aggregate_matching":True},
        "counts":{"current_winners":len(cur_winners),"prior_14_survivors":len(old_survivors),
                  "exact_current_to_prior_matches":sum(x["exact_match"] for x in matrix),
                  "current_winners_without_match":sum(not x["exact_match"] for x in matrix),
                  "prior_survivors_without_match":len(unmatched_old)},
        "matrix":matrix,
        "unmatched_prior_14":[
            {"observation_id":r["observation_id"],"fold":r["fold"],"timestamp":r["timestamp"],
             "sequence_first":r["sequence_first"],"sequence_last":r["sequence_last"],
             "entry_price":r["entry_price"],"exit_price":r["exit_price"],
             "gross_outcome":r["gross_outcome"],"lineage":r["lineage"]}
            for r in unmatched_old
        ]
    }

if __name__=="__main__":
    old=run_lineage("/tmp/old_repo","/tmp/old_trades.csv",os.environ["OLD_RAW_BLOB_SHA"],"prior_1049")
    cur=run_lineage("/tmp/current_repo","/tmp/current_trades.csv",os.environ["CURRENT_RAW_BLOB_SHA"],"current_1027")
    rec=reconcile(old,cur)
    Path("prior_1049_reconstructed.json").write_text(json.dumps(old,indent=2)+"\n")
    Path("current_1027_population_reconstructed.json").write_text(json.dumps(cur,indent=2)+"\n")
    Path("reconciliation_28_to_14_record_level.json").write_text(json.dumps(rec,indent=2)+"\n")
    with open("reconciliation_28_to_14_matrix.csv","w",newline="",encoding="utf-8") as f:
        fields=list(rec["matrix"][0].keys())
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for row in rec["matrix"]:
            row=dict(row); row["prior_observation_ids"]=";".join(row["prior_observation_ids"])
            w.writerow(row)
    print(json.dumps({"old":old["counts"],"current":cur["counts"],"reconciliation":rec["counts"]},indent=2))
