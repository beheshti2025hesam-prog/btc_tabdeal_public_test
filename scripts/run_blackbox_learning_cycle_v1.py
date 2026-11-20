#!/usr/bin/env python3
"""Run one read-only Blackbox experience-memory and tournament cycle."""
import json, os
from pathlib import Path
import sys
CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))
from scripts.runtime_paths_v1 import DATA_ROOT
from forward.blackbox_experience_memory_v1 import (
    collect_canonical_experiences, append_experience_events,
    discover_canonical_shadow_hypotheses, append_hypothesis_events,
)
from forward.blackbox_tournament_runtime_v1 import run_competition_cycle

ROOT = DATA_ROOT
DATA = ROOT / "data" / "forward"
events, source_counts = collect_canonical_experiences(ROOT)
hypotheses = discover_canonical_shadow_hypotheses(ROOT)
memory = append_experience_events(DATA / "blackbox_experience_memory_v1.jsonl", events)
hypothesis_memory = append_hypothesis_events(DATA / "blackbox_hypothesis_events_v1.jsonl", hypotheses)
tournament = run_competition_cycle(ROOT)
print(json.dumps({
    "schema": "hes_blackbox_learning_cycle_v1",
    "experience_events_seen": len(events),
    "experience_sources": source_counts,
    "experience_append": memory,
    "hypotheses_discovered": len(hypotheses),
    "hypothesis_append": hypothesis_memory,
    "tournament_status": tournament["status"],
    "hypotheses_tested": tournament["hypotheses_tested"],
    "family_evidence_status": tournament["family_evidence_audit"]["status"],
    "execution_enabled": False,
    "orders_placed": False,
    "policy_mutation_enabled": False,
    "production_approved": False,
}, sort_keys=True))
