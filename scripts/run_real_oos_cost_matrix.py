"""Execute the frozen 8-fold OOS cost/slippage protocol on real BTC_USDT data.

This is an evidence runner only: it is read-only with respect to trading and
does not tune parameters, fit models, mutate capital, or execute orders.
"""
import argparse
import json
import sys
from pathlib import Path

# Make the repository root importable when this file is executed directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.backtest.costs import CostScenario
from core.backtest.oos_cost_matrix import evaluate_oos_cost_matrix
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.real_data import RealDataBacktest


SCENARIOS = (
    CostScenario(0.0, 0.0),
    CostScenario(5.0, 2.0),
    CostScenario(10.0, 5.0),
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
        max_folds=REAL_BTC_USDT_OOS_V1.expected_fold_count,
    )
    matrix = evaluate_oos_cost_matrix(
        walk_forward, REAL_BTC_USDT_OOS_V1, SCENARIOS
    )

    if matrix.fold_count != REAL_BTC_USDT_OOS_V1.expected_fold_count:
        raise AssertionError(
            f"expected {REAL_BTC_USDT_OOS_V1.expected_fold_count} folds, "
            f"got {matrix.fold_count}"
        )

    folds = []
    for fold in walk_forward.folds:
        if not fold.train_end < fold.test_start:
            raise AssertionError(f"fold {fold.index} train/test overlap")
        folds.append(
            {
                "index": fold.index,
                "train_start": fold.train_start.isoformat(),
                "train_end": fold.train_end.isoformat(),
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "train_observations": fold.train_observations,
                "test_observations": fold.test_observations,
                "evaluated": fold.result.evaluated,
                "wins": fold.result.wins,
                "losses": fold.result.losses,
                "total_return": fold.result.total_return,
            }
        )

    measurements = [
        {
            "fold_index": row.fold_index,
            "transaction_cost_bps_per_side": row.scenario.transaction_cost_bps_per_side,
            "slippage_bps_per_side": row.scenario.slippage_bps_per_side,
            "total_net_return": row.total_net_return,
            "evaluated": row.evaluated,
            "wins": row.wins,
            "losses": row.losses,
        }
        for row in matrix.measurements
    ]
    aggregate = [
        {
            "transaction_cost_bps_per_side": row.scenario.transaction_cost_bps_per_side,
            "slippage_bps_per_side": row.scenario.slippage_bps_per_side,
            "total_net_return": row.total_net_return,
            "evaluated": row.evaluated,
            "wins": row.wins,
            "losses": row.losses,
        }
        for row in matrix.aggregate
    ]

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
        "folds": folds,
        "cost_matrix": {
            "measurement_count": len(measurements),
            "measurements": measurements,
            "aggregate": aggregate,
        },
        "safety": {
            "execution": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "capital_mutation": False,
        },
    }

    output = Path(args.output)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
