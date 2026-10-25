#!/usr/bin/env python3
"""Read-only forward paper observation; one record per unique closed 15m candle."""
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

OUT = ROOT / "data/forward/strategy_policy_v2_forward.jsonl"


def load_last_seen(path: Path) -> int | None:
    if not path.is_file():
        return None
    last = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                value = record.get("candle_close_time")
                if isinstance(value, int):
                    last = value
            except (json.JSONDecodeError, AttributeError):
                continue
    return last


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    seen = load_last_seen(OUT)
    while True:
        try:
            source = load_market_input(root=ROOT)
            rows = source["timeframes"]["15m"]
            candle_time = int(rows[-1]["close_time"])
            if candle_time != seen:
                features = {timeframe: snapshot(timeframe, bars)
                            for timeframe, bars in source["timeframes"].items()}
                proposal = evaluate(features)
                decision = enforce_final_gates(proposal)
                if (decision.decision != "NO_TRADE" or decision.direction != "NONE"
                        or decision.execution_enabled or decision.orders_placed):
                    print(json.dumps({"error": "FINAL_GATE_INVARIANT_VIOLATION",
                                      "decision": "NO_TRADE", "execution_enabled": False,
                                      "orders_placed": False}), flush=True)
                    return 3
                record = {
                    "schema": "hes_strategy_policy_v2_forward_record",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "candle_close_time": candle_time,
                    "source": source["source"],
                    "symbol": source["symbol"],
                    "features": {
                        timeframe: {key: values.get(key) for key in (
                            "last_closed_at_utc", "close", "ema50", "ema200", "rsi14",
                            "mfi14", "atr14", "close_vs_ema50", "close_vs_vwap20",
                            "close_breakout20", "candle_closed",
                        )}
                        for timeframe, values in features.items()
                    },
                    "policy_proposal": proposal.as_dict(),
                    "decision": decision.as_dict(),
                    "final_gate_version": GATE_VERSION,
                    "outcome": None,
                    "closed_at": None,
                    "execution_enabled": False,
                    "orders_placed": False,
                }
                append_record(OUT, record)
                seen = candle_time
                print(json.dumps({"candle_close_time": candle_time,
                                  "policy_proposal": proposal.decision,
                                  "final_decision": decision.decision,
                                  "gate_version": decision.gate_version,
                                  "reasons": list(decision.reasons),
                                  "execution_enabled": False, "orders_placed": False}), flush=True)
        except Exception as exc:
            print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(),
                              "error": type(exc).__name__ + ":" + str(exc)[:200],
                              "decision": "NO_TRADE", "execution_enabled": False,
                              "orders_placed": False}), flush=True)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
