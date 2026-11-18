#!/usr/bin/env python3
"""Read-only preview or explicit append of reference-only Blackbox experience memory."""
import argparse, json, os, sys
from pathlib import Path
CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_ROOT)) if str(CODE_ROOT) not in sys.path else None
from forward.blackbox_experience_memory_v1 import (collect_canonical_experiences, append_experience_events,
    discover_canonical_shadow_hypotheses, append_hypothesis_events)

ap = argparse.ArgumentParser()
ap.add_argument("--data-root", type=Path, default=Path(os.environ.get("HES_DATA_ROOT", "/opt/hes-trade-agent")))
ap.add_argument("--output", type=Path, default=None)
ap.add_argument("--append", action="store_true", help="explicitly append to the reference-only memory ledger")
ap.add_argument("--append-hypotheses", action="store_true", help="explicitly append discovery-only hypothesis events")
args = ap.parse_args()
events, source_counts = collect_canonical_experiences(args.data_root)
eligible = sum(e["training_eligible"] for e in events)
hypotheses = discover_canonical_shadow_hypotheses(args.data_root)
report = {"schema":"hes_blackbox_experience_memory_build_v1", "source_counts":source_counts,
          "discovered_hypothesis_count":len(hypotheses),
          "discovered_hypothesis_examples":[{"hypothesis_id":h["hypothesis_id"],"feature":h["discovery_metadata"]["feature"],
             "regime":h["discovery_metadata"]["regime"],"bucket":h["discovery_metadata"]["bucket"],
             "support_count":h["discovery_metadata"]["support_count"]} for h in hypotheses[:5]],
          "experience_events":len(events), "training_eligible_events":eligible,
          "four_state_counts":{s:sum(e["regime"]==s for e in events) for s in ("BULLISH","BEARISH","RANGE","NO_TRADE")},
          "experience_type_counts":{t:sum(e["experience_type"]==t for e in events) for t in
              ("TRADE_OUTCOME","NO_TRADE_COUNTERFACTUAL","REJECTED_PROPOSAL","MARKET_CONTEXT","FAMILY_RESEARCH")},
          "mode": ("APPEND_ONLY_REFERENCE_AND_HYPOTHESIS_EVENTS" if args.append and args.append_hypotheses
                   else "APPEND_ONLY_REFERENCE_INDEX" if args.append
                   else "APPEND_ONLY_HYPOTHESIS_EVENTS" if args.append_hypotheses
                   else "READ_ONLY_PREVIEW"),
          "execution_enabled":False,"orders_placed":False,"policy_mutation_enabled":False,
          "production_approved":False,"risk_gate_bypass":False}
if args.append:
    out = args.output or (args.data_root / "data" / "forward" / "blackbox_experience_memory_v1.jsonl")
    report["append_result"] = append_experience_events(out, events)
    report["output"] = str(out)
if args.append_hypotheses:
    hypothesis_path = args.data_root / "data" / "forward" / "blackbox_hypothesis_events_v1.jsonl"
    report["hypothesis_append_result"] = append_hypothesis_events(hypothesis_path, hypotheses)
    report["hypothesis_output"] = str(hypothesis_path)
print(json.dumps(report, indent=2, sort_keys=True))
