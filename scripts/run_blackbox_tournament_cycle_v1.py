#!/usr/bin/env python3
"""Run one Blackbox verified-evidence tournament cycle."""
import json, sys
from pathlib import Path
CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))
from scripts.runtime_paths_v1 import DATA_ROOT
from forward.blackbox_tournament_runtime_v1 import run_competition_cycle
report = run_competition_cycle(DATA_ROOT)
print(json.dumps({
    "status": report["status"],
    "eligible_hypotheses": report["hypotheses_with_eligible_evidence"],
    "tested": report["hypotheses_tested"],
    "family_evidence_status": report["family_evidence_audit"]["status"],
    "execution_enabled": False,
    "orders_placed": False,
    "policy_mutation_enabled": False,
}, sort_keys=True))
