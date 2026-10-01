#!/usr/bin/env python3
"""Deterministic Candidate Rule A fresh-snapshot study.

Research-only. Applies the pre-registered Rule A to every eligible OOS
observation on the exact lineage-locked snapshot. No tuning, fitting,
selection, promotion, capital mutation, or execution.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from core.backtest.costs import BacktestCostModel, CostScenario
from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalValidation, HistoricalObservation
from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.models.trade import CanonicalTrade
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision
from scripts.candidate_rule_a_research_v1 import evaluate_rule_a

CSV = Path(os.environ["HES_FROZEN_CSV"])
EXPECTED_BLOB = os.environ["FRESH_BLOB_SHA"]
EXPECTED_COMMIT = os.environ["FRESH_SOURCE_COMMIT"]
TRAIN, TEST, STEP, FOLDS = 800, 400, 400, 8
SCENARIOS = (
    CostScenario(0.0, 0.0),
    CostScenario(5.0, 2.0),
    CostScenario(10.0, 5.0),
)


def verify_blob() -> None:
    raw = CSV.read_bytes()
    actual = hashlib.sha1(f"blob {len(raw)}\\0".encode() + raw).hexdigest()
    assert actual == EXPECTED_BLOB, (actual, EXPECTED_BLOB)


def load_trades() -> tuple[list[CanonicalTrade], int, int]:
    reader = RawDataReader(active_file=str(CSV), archive_dir="__no_archive__")
    validator = RawDataValidator()
    normalizer = RawDataNormalizer()
    valid, total, invalid = [], 0, 0
    for row in reader.read_all():
        total += 1
        if validator.validate_row(row):
            invalid += 1
        else:
            valid.append(normalizer.normalize_row(row))
    valid.sort(key=lambda t: (t.timestamp, t.sequence or -1))
    return valid, total, invalid


def main() -> None:
    verify_blob()
    trades, rows_read, rows_invalid = load_trades()
    candles = TradeCandleAggregator(60).aggregate(trades)

    pressure: dict[tuple[str, int], tuple[float, float]] = {}
    for candle in candles:
        bucket = [
            t for t in trades
            if t.symbol == candle.symbol
            and candle.start <= t.timestamp < candle.end
        ]
        buy = sum(t.quantity for t in bucket if t.side == "buy")
        sell = sum(t.quantity for t in bucket if t.side == "sell")
        total = buy + sell
        pressure[(candle.symbol, int(candle.start.timestamp()))] = (
            buy / total if total else 0.0,
            buy - sell,
        )

    observations: list[dict] = []
    for i in range(len(candles) - 1):
        c, n = candles[i], candles[i + 1]
        if c.symbol != n.symbol or n.start != c.end:
            continue
        br, delta = pressure[(c.symbol, int(c.start.timestamp()))]
        direction = evaluate_rule_a(br, delta, float(c.trade_count))
        decision = {
            "LONG": BaselineDecision.LONG,
            "SHORT": BaselineDecision.SHORT,
            "NO_TRADE": BaselineDecision.NO_TRADE,
        }[direction]
        observations.append({
            "timestamp": c.end,
            "decision": decision,
            "risk": RiskDecision.ALLOW_SIGNAL,
            "entry_price": c.close,
            "exit_price": n.close,
            "buy_ratio": br,
            "buy_sell_delta": delta,
            "trade_count": c.trade_count,
            "direction": direction,
        })

    if len(observations) < TRAIN + FOLDS * TEST:
        raise AssertionError(
            f"fresh snapshot has {len(observations)} candidate observations; "
            f"requires at least {TRAIN + FOLDS * TEST}"
        )

    oos = observations[TRAIN:TRAIN + FOLDS * TEST]
    folds = []
    all_oos = []

    for fold in range(FOLDS):
        test = oos[fold * STEP: fold * STEP + TEST]
        if len(test) != TEST:
            raise AssertionError(f"fold {fold} has {len(test)} observations")
        samples = tuple(
            BacktestSample(
                timestamp=r["timestamp"],
                decision=r["decision"],
                risk=r["risk"],
                entry_price=r["entry_price"],
                exit_price=r["exit_price"],
            )
            for r in test
        )
        result = HistoricalValidation().run(
            [HistoricalObservation(timestamp=s.timestamp, sample=s) for s in samples]
        )
        folds.append({
            "fold_index": fold,
            "train_observations": TRAIN,
            "test_observations": TEST,
            "evaluated": result.evaluated,
            "wins": result.wins,
            "losses": result.losses,
            "no_trade": result.no_trade,
            "gross_return": result.total_return,
            "long_count": sum(r["direction"] == "LONG" for r in test),
            "short_count": sum(r["direction"] == "SHORT" for r in test),
            "no_trade_count": sum(r["direction"] == "NO_TRADE" for r in test),
        })
        all_oos.extend(test)

    cost_rows = []
    for scenario in SCENARIOS:
        model = BacktestCostModel(
            transaction_cost_bps_per_side=scenario.transaction_cost_bps_per_side,
            slippage_bps_per_side=scenario.slippage_bps_per_side,
        )
        total = evaluated = wins = losses = 0
        fold_rows = []
        for fold in range(FOLDS):
            test = oos[fold * STEP: fold * STEP + TEST]
            values = []
            for r in test:
                if r["decision"] is BaselineDecision.NO_TRADE:
                    continue
                value = model.net_return(BacktestSample(
                    timestamp=r["timestamp"], decision=r["decision"], risk=r["risk"],
                    entry_price=r["entry_price"], exit_price=r["exit_price"],
                ))
                values.append(value)
            fold_total = sum(values)
            fold_rows.append({
                "fold_index": fold,
                "evaluated": len(values),
                "wins": sum(v > 0 for v in values),
                "losses": sum(v < 0 for v in values),
                "net_return": fold_total,
            })
            total += fold_total
            evaluated += len(values)
            wins += sum(v > 0 for v in values)
            losses += sum(v < 0 for v in values)
        cost_rows.append({
            "transaction_cost_bps_per_side": scenario.transaction_cost_bps_per_side,
            "slippage_bps_per_side": scenario.slippage_bps_per_side,
            "evaluated": evaluated,
            "wins": wins,
            "losses": losses,
            "total_net_return": total,
            "folds": fold_rows,
        })

    assert len(all_oos) == FOLDS * TEST
    assert sum(x["evaluated"] for x in folds) == sum(x["evaluated"] for x in cost_rows[0]["folds"])

    result = {
        "status": "CANDIDATE_RULE_A_PERFORMANCE_STUDY_REVIEW_ONLY",
        "candidate_id": "CANDIDATE_RESEARCH_V1_RULE_A",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_COMMIT,
        },
        "protocol": {
            "train": TRAIN, "test": TEST, "step": STEP, "folds": FOLDS,
            "shuffle": False, "threshold_tuning": False, "model_fitting": False,
        },
        "input_audit": {
            "rows_read": rows_read,
            "rows_invalid": rows_invalid,
            "candles": len(candles),
            "candidate_observations": len(observations),
            "oos_observations": len(oos),
        },
        "rule": {
            "long": "buy_ratio > 0.5 AND buy_sell_delta > 0",
            "short": "buy_ratio < 0.5 AND buy_sell_delta < 0",
            "otherwise": "NO_TRADE",
            "trade_count": "finite/validity-only; no directional threshold",
        },
        "population": {
            "oos": len(oos),
            "long": sum(r["direction"] == "LONG" for r in oos),
            "short": sum(r["direction"] == "SHORT" for r in oos),
            "no_trade": sum(r["direction"] == "NO_TRADE" for r in oos),
        },
        "folds": folds,
        "cost_matrix": cost_rows,
        "claim_boundary": {
            "predictive_performance_established": False,
            "signal_created": False,
            "promotion_decision": False,
            "live_execution": False,
            "wallet_operations": False,
        },
    }
    Path("candidate_rule_a_performance_study_v1.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
