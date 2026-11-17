#!/usr/bin/env python3
"""Read-only family learning bridge; reports evidence and gates model training."""
from __future__ import annotations
import json, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
CODE_ROOT=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get("HES_DATA_ROOT","/opt/hes-trade-agent")).expanduser().resolve()
JOURNAL=ROOT/"data/forward/indicator_strategy_shadow_journal_v1.jsonl"
OUTCOMES=ROOT/"data/forward/indicator_strategy_shadow_outcomes_v1.jsonl"
FORWARD_JOURNAL=ROOT/"data/forward/indicator_strategy_forward_paper_journal_v1.jsonl"
FORWARD_OUTCOMES=ROOT/"data/forward/indicator_strategy_forward_paper_outcomes_v1.jsonl"
REPORT=ROOT/"data/forward/indicator_strategy_learning_v1_report.json"
MIN_RESOLVED_FOR_TRAINING=100

def read(path):
    if not path.exists(): return []
    rows=[]
    for n,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip(): raise ValueError(f"BLANK_LEDGER_LINE:{path.name}:{n}")
        item=json.loads(line)
        if not isinstance(item,dict): raise ValueError(f"INVALID_LEDGER_ROW:{path.name}:{n}")
        rows.append(item)
    return rows

def build_report(journal_path=JOURNAL, outcomes_path=OUTCOMES, report_path=REPORT,
                 forward_journal_path=FORWARD_JOURNAL, forward_outcomes_path=FORWARD_OUTCOMES):
    decisions=read(Path(journal_path)); outcomes=read(Path(outcomes_path))
    forward_decisions=read(Path(forward_journal_path)); forward_outcomes=read(Path(forward_outcomes_path))
    by_id={x.get("event_id"):x for x in decisions if x.get("event_id")}
    grouped=defaultdict(list); unmatched=0; ineligible=0
    for o in outcomes:
        d=by_id.get(o.get("candidate_event_id"))
        if d is None: unmatched+=1; continue
        if d.get("strategy_family_id")!="indicator_strategy" or d.get("research_only") is not True: ineligible+=1; continue
        if (o.get("research_only") is not True or
            not (o.get("training_label_eligible") is True or o.get("research_label_eligible") is True) or
            o.get("net_return_pct_by_cost_bps",{}).get("20") is None): continue
        grouped[(o.get("strategy_variant_id"),o.get("market_regime"))].append(o)
    variants={}
    for (variant,regime),rows in sorted(grouped.items()):
        resolved=[x for x in rows if x.get("outcome") in ("STOP_LOSS","TAKE_PROFIT","TIMEOUT")]
        wins=sum(float(x["net_return_pct_by_cost_bps"]["20"])>0 for x in resolved)
        losses=sum(float(x["net_return_pct_by_cost_bps"]["20"])<0 for x in resolved)
        flats=len(resolved)-wins-losses
        key=variant or "UNKNOWN"
        slot=variants.setdefault(key,{"by_regime":{},"resolved":0,"wins":0,"losses":0,"flats":0})
        slot["by_regime"][regime or "UNKNOWN"]={"resolved":len(resolved),"wins":wins,"losses":losses,"flats":flats,
            "win_rate_pct":round(100*wins/len(resolved),2) if resolved else None}
        slot["resolved"]+=len(resolved);slot["wins"]+=wins;slot["losses"]+=losses;slot["flats"]+=flats
    for slot in variants.values():
        slot["win_rate_pct"]=round(100*slot["wins"]/slot["resolved"],2) if slot["resolved"] else None
        slot["research_status"]="DIAGNOSTIC_ONLY_HISTORICAL_REPLAY"
    forward_by_id={x.get("event_id"):x for x in forward_decisions if x.get("event_id")}
    forward_groups=defaultdict(list); forward_unmatched=0; forward_short_unscored=0
    for o in forward_outcomes:
        d=forward_by_id.get(o.get("candidate_event_id"))
        if d is None: forward_unmatched+=1; continue
        if d.get("strategy_family_id")!="indicator_strategy" or d.get("research_only") is not True or o.get("research_only") is not True: continue
        if o.get("direction")=="SHORT": forward_short_unscored+=1; continue
        if o.get("economics_status")!="ASSUMPTION_BASED_SPOT_REFERENCE": continue
        if o.get("net_return_pct_assumption_20bps") is None: continue
        forward_groups[(o.get("strategy_variant_id"),o.get("market_regime"))].append(o)
    forward_variants={}
    for (variant,regime),rows in sorted(forward_groups.items()):
        vals=[float(x["net_return_pct_assumption_20bps"]) for x in rows]
        wins=sum(v>0 for v in vals); losses=sum(v<0 for v in vals); flats=len(vals)-wins-losses
        slot=forward_variants.setdefault(variant or "UNKNOWN",{"by_regime":{},"resolved":0,"wins":0,"losses":0,"flats":0,"net_return_pct_sum":0.0})
        slot["by_regime"][regime or "UNKNOWN"]={"resolved":len(vals),"wins":wins,"losses":losses,"flats":flats,
            "win_rate_pct":round(100*wins/len(vals),2) if vals else None,
            "mean_net_return_pct_assumption_20bps":round(sum(vals)/len(vals),8) if vals else None}
        slot["resolved"]+=len(vals);slot["wins"]+=wins;slot["losses"]+=losses;slot["flats"]+=flats;slot["net_return_pct_sum"]+=sum(vals)
    for slot in forward_variants.values():
        slot["win_rate_pct"]=round(100*slot["wins"]/slot["resolved"],2) if slot["resolved"] else None
        slot["mean_net_return_pct_assumption_20bps"]=round(slot["net_return_pct_sum"]/slot["resolved"],8) if slot["resolved"] else None
        slot["status"]="FORWARD_PAPER_DIAGNOSTIC_ONLY"
    eligible_forward=[]
    for o in outcomes:
        linked=by_id.get(o.get("candidate_event_id"))
        if (linked is not None and linked.get("performance_eligible") is True and linked.get("research_only") is not True
            and o.get("training_label_eligible") is True and o.get("performance_eligible") is True
            and o.get("research_only") is not True and o.get("outcome") in ("STOP_LOSS","TAKE_PROFIT","TIMEOUT")):
            eligible_forward.append(o)
    training_by_variant={}
    for o in eligible_forward:
        key=o.get("strategy_variant_id") or "UNKNOWN"
        training_by_variant[key]=training_by_variant.get(key,0)+1
    eligible_forward_count=len(eligible_forward)
    training_ready=any(n>=MIN_RESOLVED_FOR_TRAINING for n in training_by_variant.values())
    result={"schema":"hes_indicator_strategy_learning_report_v1","generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"READ_ONLY_EVIDENCE_ATTRIBUTION","decision_records":len(decisions),"outcome_records":len(outcomes),
        "unmatched_outcomes":unmatched,"ineligible_records":ineligible,"variants":variants,
        "forward_paper":{"decision_records":len(forward_decisions),"outcome_records":len(forward_outcomes),
            "unmatched_outcomes":forward_unmatched,"short_outcomes_not_economically_scored":forward_short_unscored,
            "variants":forward_variants,"training_eligible_labels":0,"note":"Separate forward-paper diagnostic cohort; not production-performance eligible and not used for model training."},
        "training_gate":{"minimum_resolved_per_variant":MIN_RESOLVED_FOR_TRAINING,
            "eligible_forward_paper_labels":eligible_forward_count,"eligible_forward_labels_by_variant":training_by_variant,
            "status":"READY_FOR_TRAINING_REVIEW" if training_ready else "TRAINING_BLOCKED_NO_ELIGIBLE_FORWARD_PAPER_LABELS",
            "model_trained":False,"threshold_tuning":False,"holdout_reselection":False},
        "safety":{"policy_mutation_enabled":False,"execution_enabled":False,"orders_placed":False,"risk_gate_bypass":False},
        "limitations":["This shadow ledger is separate from production decisions and is not performance-eligible.",
            "Backtest labels are exploratory historical labels, not independent forward paper outcomes.",
            "No strategy is promoted by this report."]}
    report_path=Path(report_path); report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result
if __name__=="__main__":
    x=build_report()
    print(json.dumps({"status":x["training_gate"]["status"],"decision_records":x["decision_records"],
        "outcome_records":x["outcome_records"],"variants":x["variants"],"report":str(REPORT)},indent=2))
