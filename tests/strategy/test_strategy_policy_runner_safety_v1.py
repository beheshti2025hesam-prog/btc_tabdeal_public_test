import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_strategy_policy_v2_paper import (
    append_record as append_paper_record, load_last_seen, should_process_candle,
)
from scripts.run_strategy_policy_v2_forward_eval import (
    GATE_VERSION, POLICY_VERSION, STATE_SCHEMA, OBS_SCHEMA,
    LegacyStateRequiresReview, empty_state, load_state, load_observation_progress,
    reconcile_state_with_observations, should_observe_candle, append_record,
)


def test_paper_runner_loads_last_candle_for_exact_current_policy(tmp_path):
    path = tmp_path / "paper.jsonl"
    path.write_text(
        json.dumps({"schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 100,
                    "policy_version": POLICY_VERSION, "final_gate_version": GATE_VERSION}) + "\n" +
        json.dumps({"schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 200,
                    "policy_version": POLICY_VERSION, "final_gate_version": GATE_VERSION}) + "\n",
        encoding="utf-8",
    )
    assert load_last_seen(path) == 200
    assert not should_process_candle(200, load_last_seen(path))
    assert not should_process_candle(150, load_last_seen(path))
    assert should_process_candle(300, load_last_seen(path))


def test_paper_runner_ignores_older_policy_cohort(tmp_path):
    path = tmp_path / "paper.jsonl"
    path.write_text(json.dumps({
        "schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 900,
        "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
        "final_gate_version": GATE_VERSION,
    }) + "\n", encoding="utf-8")
    assert load_last_seen(path) is None
    assert should_process_candle(900, load_last_seen(path))


def test_paper_append_then_restart_does_not_duplicate_same_candle(tmp_path):
    path = tmp_path / "paper.jsonl"
    append_paper_record(path, {
        "schema": "hes_strategy_policy_v2_forward_record", "candle_close_time": 200,
        "policy_version": POLICY_VERSION, "final_gate_version": GATE_VERSION,
    })
    restarted_last_seen = load_last_seen(path)
    assert restarted_last_seen == 200
    assert not should_process_candle(200, restarted_last_seen)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_legacy_evaluator_state_is_not_resumed_or_overwritten(tmp_path):
    path = tmp_path / "legacy-state.json"
    original = {"last_seen": 123, "active": [{"direction": "LONG"}], "wins": 1}
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(LegacyStateRequiresReview, match="LEGACY_STATE_REQUIRES_MANUAL_REVIEW"):
        load_state(path)
    assert path.read_text(encoding="utf-8") == before


def test_current_version_state_with_active_candidate_requires_manual_review(tmp_path):
    path = tmp_path / "active-state.json"
    state = empty_state()
    state["active"] = [{"candidate_id": "candidate-1", "direction": "LONG"}]
    path.write_text(json.dumps(state), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(LegacyStateRequiresReview, match="ACTIVE_CANDIDATES_REQUIRE_MANUAL_REVIEW"):
        load_state(path)
    assert path.read_text(encoding="utf-8") == before


def test_new_evaluator_state_is_explicitly_versioned_and_empty(tmp_path):
    state = load_state(tmp_path / "missing-state.json")
    assert state["schema"] == STATE_SCHEMA
    assert state["policy_version"] == POLICY_VERSION
    assert state["final_gate_version"] == GATE_VERSION
    assert state["active"] == [] and state["observations"] == 0


def test_observation_log_rejects_legacy_policy_records(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text(json.dumps({
        "schema": OBS_SCHEMA, "candle_close_time": 100,
        "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
        "final_gate_version": GATE_VERSION,
    }) + "\n", encoding="utf-8")
    with pytest.raises(LegacyStateRequiresReview, match="OBSERVATION_LOG_VERSION_REQUIRES_REVIEW"):
        load_observation_progress(path)


def test_append_then_restart_recovers_crash_window_without_duplicate(tmp_path):
    path = tmp_path / "observations.jsonl"
    append_record(path, {
        "schema": OBS_SCHEMA, "candle_close_time": 200,
        "policy_version": POLICY_VERSION, "final_gate_version": GATE_VERSION,
        "decision": {"decision": "NO_TRADE", "direction": "NONE"},
        "execution_enabled": False, "orders_placed": False,
    })
    # Simulate death after fsync of the observation but before state-file replacement.
    restarted_state = reconcile_state_with_observations(empty_state(), path)
    assert restarted_state["last_seen"] == 200
    assert restarted_state["observations"] == 1
    assert not should_observe_candle(200, restarted_state["last_seen"])
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_observation_progress_rejects_non_fail_closed_records(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text(json.dumps({
        "schema": OBS_SCHEMA, "candle_close_time": 200,
        "policy_version": POLICY_VERSION, "final_gate_version": GATE_VERSION,
        "decision": {"decision": "LONG", "direction": "LONG"},
        "execution_enabled": False, "orders_placed": False,
    }) + "\n", encoding="utf-8")
    with pytest.raises(LegacyStateRequiresReview, match="OBSERVATION_LOG_SAFETY_REQUIRES_REVIEW"):
        load_observation_progress(path)


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
