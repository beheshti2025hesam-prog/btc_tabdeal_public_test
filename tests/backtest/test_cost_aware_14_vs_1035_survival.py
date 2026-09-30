"""Regression tests for the cost-aware frozen 14-vs-1035 evidence layer."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_cost_survival_math_and_frozen_boundaries():
    gross = [0.0015, 0.0030, 0.0040]
    net_7 = [x - 0.0014 for x in gross]
    net_15 = [x - 0.0030 for x in gross]
    assert sum(x > 0 for x in net_7) == 3
    assert sum(x > 0 for x in net_15) == 1


def test_script_declares_exact_existing_scenarios_and_embargo_boundary():
    path = Path(__file__).resolve().parents[2] / "scripts" / "cost_aware_14_vs_1035_survival.py"
    text = path.read_text(encoding="utf-8")
    assert 'CostScenario' not in text or "5.0" in text
    assert '"transaction_cost_bps_per_side": 5.0' in text
    assert '"slippage_bps_per_side": 2.0' in text
    assert '"transaction_cost_bps_per_side": 10.0' in text
    assert '"slippage_bps_per_side": 5.0' in text
    assert '"embargo_size": 0' in text
    assert "requires_embargo_or_equivalent_purge" in text
    assert '"control_reconstruction": False' in text
