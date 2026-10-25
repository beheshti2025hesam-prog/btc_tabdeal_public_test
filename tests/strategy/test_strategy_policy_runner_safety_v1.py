import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_strategy_policy_v2_paper import load_last_seen
from scripts.run_strategy_policy_v2_forward_eval import (
    GATE_VERSION,
    POLICY_VERSION,
    STATE_SCHEMA,
    LegacyStateRequiresReview,
    empty_state,
    load_state,
)


def test_paper_runner_loads_last_candle_to_avoid_restart_duplicate(tmp_path):
    path = tmp_path / "paper.jsonl"
    path.write_text(
        json.dumps({"schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 100}) + "\n" +
        json.dumps({"schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 200}) + "\n",
        encoding="utf-8",
    )
    assert load_last_seen(path) == 200


def test_legacy_evaluator_state_is_not_resumed_or_overwritten(tmp_path):
    path = tmp_path / "legacy-state.json"
    original = {"last_seen": 123, "active": [{"direction": "LONG"}], "wins": 1}
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(LegacyStateRequiresReview, match="LEGACY_STATE_REQUIRES_MANUAL_REVIEW"):
        load_state(path)
    assert path.read_text(encoding="utf-8") == before


def test_new_evaluator_state_is_explicitly_versioned_and_empty(tmp_path):
    state = load_state(tmp_path / "missing-state.json")
    assert state["schema"] == STATE_SCHEMA
    assert state["policy_version"] == POLICY_VERSION
    assert state["final_gate_version"] == GATE_VERSION
    assert state["active"] == [] and state["observations"] == 0


def test_runner_modules_import_without_starting_loops(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["HES_TRADE_AGENT_ROOT"] = str(tmp_path)
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-c",
         "import scripts.run_strategy_policy_v2_paper; import scripts.run_strategy_policy_v2_forward_eval"],
        cwd=root, env=env, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data/forward/strategy_policy_v2_forward.jsonl").exists()
    assert not (tmp_path / "data/forward/strategy_policy_v2_eval_state.json").exists()
