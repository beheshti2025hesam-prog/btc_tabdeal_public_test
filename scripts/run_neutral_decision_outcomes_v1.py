#!/usr/bin/env python3
"""One-shot idempotent runner for the HES NO_TRADE outcome tracker."""
import json, sys
from pathlib import Path
CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_ROOT))
from scripts.runtime_paths_v1 import DATA_ROOT
ROOT = DATA_ROOT
from forward.neutral_decision_outcomes_v1 import run
if __name__ == "__main__":
    print(json.dumps(run(ROOT), indent=2, sort_keys=True))
