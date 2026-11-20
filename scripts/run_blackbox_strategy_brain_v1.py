#!/usr/bin/env python3
"""Generate the read-only Blackbox strategy brain readiness artifact."""
import json
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from scripts.runtime_paths_v1 import DATA_ROOT
from forward.blackbox_strategy_brain_v1 import assess_blackbox_readiness

report = assess_blackbox_readiness(data_root=DATA_ROOT)
out = DATA_ROOT / "data" / "forward" / "blackbox_strategy_brain_v1_readiness.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({
    "status": report["status"],
    "blocking_reasons": report["blocking_reasons"],
    "resolved_outcomes": report["training_evidence"]["matured_gate_approved_resolved_outcomes"],
    "output": str(out),
    "execution_enabled": False,
}, sort_keys=True))
