#!/usr/bin/env python3
"""Validate the frozen protocol-reconciliation artifact.

Review-only: this validator does not execute v2, touch Raw data, select winners,
or change any threshold.
"""
import json
from pathlib import Path

p = Path("evidence/protocol_reconciliation_v1.json")
d = json.loads(p.read_text(encoding="utf-8"))

assert d["status"] == "PROTOCOL_RECONCILIATION_REVIEW_ONLY"
assert d["decision_boundary"]["v2_executed"] is False
assert d["decision_boundary"]["threshold_changed"] is False
assert d["decision_boundary"]["winner_selected_manually"] is False
assert d["decision_boundary"]["subset_selected_manually"] is False

pc = d["protocol_core"]
assert pc["fold_partition"] == {"train": 800, "test": 400, "step": 400, "folds": 8}
assert pc["winner_rule"]["gross_return_strictly_greater_than"] == 0.0014
assert pc["control_rule"]["gross_return_less_than_or_equal_to"] == 0.0014

hist = d["historical_reconciliation"]
assert len(hist) == 2
old, fresh = hist
assert (old["evaluated_oos"], old["winners"], old["controls"]) == (1049, 14, 1035)
assert (fresh["evaluated_oos"], fresh["winners"], fresh["controls"]) == (1010, 2, 1008)
assert old["snapshot_blob"] != fresh["snapshot_blob"]
assert d["subset_or_snapshot_test"]["predefined_winner_subset_found"] is False
assert d["subset_or_snapshot_test"]["manual_filter_found"] is False
assert d["gate"]["v2_allowed_now"] is False

print("PROTOCOL_RECONCILIATION_VALID")
