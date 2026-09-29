"""Run the frozen real BTC_USDT OOS cost/slippage matrix as evidence."""
import argparse
import json
from pathlib import Path

from core.backtest.oos_cost_matrix import OOSCostScenario, evaluate_oos_cost_matrix
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.execution_realism import ExecutionCostConfig
from core.backtest.real_data import RealDataBacktest


SCENARIOS = (
    OOSCostScenario("zero-cost", ExecutionCostConfig()),
    OOSCostScenario(
        "5bps-fee-2bps-slippage",
        ExecutionCostConfig(fee_bps_per_side=5.0, slippage_bps_per_side=2.0),
    ),
    OOSCostScenario(
        "10bps-fee-5bps-slippage",
        ExecutionCostConfig(fee_bps_per_side=10.0, slippage_bps_per_side=5.0),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/trades.csv")
    parser.add_argument("--output", default="oos_cost_matrix_evidence.json")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.is_file():
        raise FileNotFoundError(f"real-data input not found: {path}")

    runner = RealDataBacktest(str(path))
    walk_forward = runner.run_walk_forward(
        train_size=REAL_BTC_USDT_OOS_V1.train_size,
        test_size=REAL_BTC_USDT_OOS_V1.test_size,
        step_size=REAL_BTC_USDT_OOS_V1.step_size,
        embargo_size=REAL_BTC_USDT_OOS_V1.embargo_size,
    )
    matrix = evaluate_oos_cost_matrix(
        walk_forward, REAL_BTC_USDT_OOS_V1, SCENARIOS
    )

    evidence = {
        "protocol": {
            "protocol_id": REAL_BTC_USDT_OOS_V1.protocol_id,
            "train_size": REAL_BTC_USDT_OOS_V1.train_size,
            "test_size": REAL_BTC_USDT_OOS_V1.test_size,
            "step_size": REAL_BTC_USDT_OOS_V1.step_size,
            "embargo_size": REAL_BTC_USDT_OOS_V1.embargo_size,
            "expected_fold_count": REAL_BTC_USDT_OOS_V1.expected_fold_count,
        },
        "input": str(path),
        "walk_forward": {
            "fold_count": len(walk_forward.folds),
            "samples": walk_forward.samples,
            "evaluated": walk_forward.evaluated,
            "wins": walk_forward.wins,
            "losses": walk_forward.losses,
            "total_return": walk_forward.total_return,
            "win_rate": walk_forward.win_rate,
        },
        "measurements": [
            {
                "fold_index": row.fold_index,
                "scenario": row.scenario.name,
                "fee_bps_per_side": row.scenario.config.fee_bps_per_side,
                "spread_bps": row.scenario.config.spread_bps,
                "slippage_bps_per_side": row.scenario.config.slippage_bps_per_side,
                "total_net_return": row.total_net_return,
                "evaluated": row.evaluated,
                "wins": row.wins,
                "losses": row.losses,
                "compounded_return": row.compounded_return,
            }
            for row in matrix.measurements
        ],
        "aggregate": [
            {
                "scenario": row.scenario.name,
                "fee_bps_per_side": row.scenario.config.fee_bps_per_side,
                "spread_bps": row.scenario.config.spread_bps,
                "slippage_bps_per_side": row.scenario.config.slippage_bps_per_side,
                "total_net_return": row.total_net_return,
                "evaluated": row.evaluated,
                "wins": row.wins,
                "losses": row.losses,
                "compounded_return": row.compounded_return,
            }
            for row in matrix.aggregate
        ],
        "safety": {
            "execution": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "capital_mutation": False,
        },
    }
    Path(args.output).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
