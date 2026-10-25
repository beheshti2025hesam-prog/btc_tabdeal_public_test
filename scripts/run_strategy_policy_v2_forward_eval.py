#!/usr/bin/env python3
"""Forward-only evaluator with a mandatory final NO_TRADE gate; never places orders."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("HES_TRADE_AGENT_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input
from forward.strategy_policy_gate_v1 import GATE_VERSION, enforce_final_gates
from forward.strategy_policy_v2 import evaluate, POLICY_VERSION
from scripts.analyze_gateio_snapshot_v1 import snapshot

BASE = ROOT / "data/forward"
STATE = BASE / "strategy_policy_v2_eval_state.json"
OBS = BASE / "strategy_policy_v2_eval_observations.jsonl"
REPORT = BASE / "strategy_policy_v2_eval_report.json"
STATE_SCHEMA = "hes_strategy_policy_v2_eval_state_v1"


class LegacyStateRequiresReview(RuntimeError):
    pass


def empty_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "policy_version": POLICY_VERSION,
        "final_gate_version": GATE_VERSION,
        "last_seen": None,
        "active": [],
        "observations": 0,
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyStateRequiresReview("EVALUATOR_STATE_UNREADABLE") from exc
    if (state.get("schema") != STATE_SCHEMA
            or state.get("policy_version") != POLICY_VERSION
            or state.get("final_gate_version") != GATE_VERSION):
        raise LegacyStateRequiresReview("LEGACY_STATE_REQUIRES_MANUAL_REVIEW")
    if state.get("active"):
        raise LegacyStateRequiresReview("ACTIVE_CANDIDATES_REQUIRE_MANUAL_REVIEW")
    return state


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    try:
        state = load_state(STATE)
    except LegacyStateRequiresReview as exc:
        print(json.dumps({"schema": "hes_strategy_policy_v2_eval_start_blocked",
                          "error": str(exc), "decision": "NO_TRADE",
                          "execution_enabled": False, "orders_placed": False}), flush=True)
        return 3

    print("EVALUATOR_STARTED " + POLICY_VERSION + " " + GATE_VERSION, flush=True)
    while True:
        try:
            source = load_market_input(root=ROOT)
            frames = source["timeframes"]
            candle_time = int(frames["15m"][-1]["close_time"])
            if candle_time != state.get("last_seen"):
                features = {timeframe: snapshot(timeframe, rows) for timeframe, rows in frames.items()}
                proposal = evaluate(features)
                decision = enforce_final_gates(proposal)
                if (decision.decision != "NO_TRADE" or decision.direction != "NONE"
                        or decision.execution_enabled or decision.orders_placed):
                    print(json.dumps({"error": "FINAL_GATE_INVARIANT_VIOLATION",
                                      "decision": "NO_TRADE", "execution_enabled": False,
                                      "orders_placed": False}), flush=True)
                    return 3
                observation = {
                    "schema": "hes_strategy_policy_v2_gated_observation",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "candle_close_time": candle_time,
                    "source": source["source"],
                    "symbol": source["symbol"],
                    "policy_version": POLICY_VERSION,
                    "final_gate_version": GATE_VERSION,
                    "policy_proposal": proposal.as_dict(),
                    "decision": decision.as_dict(),
                    "outcome": None,
                    "execution_enabled": False,
                    "orders_placed": False,
                }
                append_record(OBS, observation)
                state["last_seen"] = candle_time
                state["observations"] = int(state.get("observations", 0)) + 1
                write_json_atomic(STATE, state)

            report = {
                "schema": "hes_strategy_policy_v2_forward_evaluation",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": source["source"],
                "symbol": source["symbol"],
                "closed_15m_candle_time": candle_time,
                "policy_version": POLICY_VERSION,
                "final_gate_version": GATE_VERSION,
                "observations": state["observations"],
                "active_candidates": 0,
                "resolved_trades": 0,
                "resolved_win_rate_pct": None,
                "target_win_rate_pct": 90.0,
                "target_met": False,
                "minimum_resolved_trades_for_target_claim": 30,
                "directional_candidates_blocked_until_gates_wired": True,
                "execution_enabled": False,
                "orders_placed": False,
                "caveat": "Forward paper observation only; no directional candidates or live trading until independent structure, confirmation, and risk gates are approved.",
            }
            write_json_atomic(REPORT, report)
            print(json.dumps({"candle": candle_time, "observations": state["observations"],
                              "final_decision": "NO_TRADE", "gate_version": GATE_VERSION,
                              "execution_enabled": False, "orders_placed": False}), flush=True)
        except Exception as exc:
            print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(),
                              "error": type(exc).__name__ + ":" + str(exc)[:180],
                              "decision": "NO_TRADE", "execution_enabled": False,
                              "orders_placed": False}), flush=True)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
