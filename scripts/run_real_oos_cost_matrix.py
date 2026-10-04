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

from core.backtest.costs import BacktestCostModel, CostScenario
from core.backtest.oos_cost_matrix import evaluate_oos_cost_matrix
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.real_data import RealDataBacktest


SCENARIOS = (
    CostScenario(0.0, 0.0),
    CostScenario(5.0, 2.0),
    CostScenario(10.0, 5.0),
)
SURVIVAL_THRESHOLD_BPS = 14.0


def _gross_distribution(folds):
    """Count every evaluated gross return into mutually exclusive bps bands."""
    distribution = {
        "negative_below_0bps": 0,
        "zero_to_14bps_inclusive": 0,
        "above_14bps": 0,
        "zero_exact": 0,
        "positive_up_to_14bps": 0,
    }
    fold_rows = []

    model = BacktestCostModel()
    for fold in folds:
        row = {
            "fold_index": fold.index,
            "evaluated": 0,
            "negative_below_0bps": 0,
            "zero_to_14bps_inclusive": 0,
            "above_14bps": 0,
            "zero_exact": 0,
            "positive_up_to_14bps": 0,
            "gross_wins": 0,
            "survived_above_14bps": 0,
            "survival_rate_of_gross_wins": 0.0,
        }
        for sample in fold.test_samples:
            if sample.decision.value == "NO_TRADE" or sample.risk.value == "VETO":
                continue
            gross_bps = model.gross_return(sample) * 10_000.0
            row["evaluated"] += 1
            if gross_bps < 0:
                row["negative_below_0bps"] += 1
            elif gross_bps <= SURVIVAL_THRESHOLD_BPS:
                row["zero_to_14bps_inclusive"] += 1
                if gross_bps == 0:
                    row["zero_exact"] += 1
                else:
                    row["positive_up_to_14bps"] += 1
            else:
                row["above_14bps"] += 1

        row["gross_wins"] = row["positive_up_to_14bps"] + row["above_14bps"]
        row["survived_above_14bps"] = row["above_14bps"]
        if row["gross_wins"]:
            row["survival_rate_of_gross_wins"] = (
                row["survived_above_14bps"] / row["gross_wins"]
            )
        fold_rows.append(row)

        for key in distribution:
            distribution[key] += row[key]

    total_evaluated = sum(row["evaluated"] for row in fold_rows)
    if (
        distribution["negative_below_0bps"]
        + distribution["zero_to_14bps_inclusive"]
        + distribution["above_14bps"]
        != total_evaluated
    ):
        raise AssertionError("gross-return bands do not partition evaluated samples")

    if total_evaluated != 1049:
        raise AssertionError(
            f"expected 1049 evaluated gross samples, got {total_evaluated}"
        )

    if distribution["negative_below_0bps"] != 479:
        raise AssertionError(
            f"expected 479 gross losses below 0bps, got "
            f"{distribution['negative_below_0bps']}"
        )

    if distribution["above_14bps"] != 14:
        raise AssertionError(
            f"expected 14 gross returns above 14bps, got "
            f"{distribution['above_14bps']}"
        )

    if distribution["zero_to_14bps_inclusive"] != 556:
        raise AssertionError(
            f"expected 556 gross returns in 0-14bps inclusive band, got "
            f"{distribution['zero_to_14bps_inclusive']}"
        )

    if distribution["zero_exact"] != 42:
        raise AssertionError(
            f"expected 42 exact-zero gross returns, got {distribution['zero_exact']}"
        )

    return {
        "threshold_bps": SURVIVAL_THRESHOLD_BPS,
        "aggregate": distribution,
        "folds": fold_rows,
        "reconciliation": {
            "negative_below_0bps": distribution["negative_below_0bps"],
            "zero_to_14bps_inclusive": distribution["zero_to_14bps_inclusive"],
            "above_14bps": distribution["above_14bps"],
            "sum": (
                distribution["negative_below_0bps"]
                + distribution["zero_to_14bps_inclusive"]
                + distribution["above_14bps"]
            ),
            "expected_evaluated": 1049,
            "matches_1049": total_evaluated == 1049,
            "gross_wins": (
                distribution["positive_up_to_14bps"] + distribution["above_14bps"]
            ),
            "survived_above_14bps": distribution["above_14bps"],
            "survival_rate_of_gross_wins": (
                distribution["above_14bps"]
                / (
                    distribution["positive_up_to_14bps"]
                    + distribution["above_14bps"]
                )
            ),
        },
    }


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

    gross_audit = _gross_distribution(walk_forward.folds)
    net_survival = {
        "threshold_round_trip_bps": SURVIVAL_THRESHOLD_BPS,
        "positive_net_after_14bps_count": gross_audit["reconciliation"]["survived_above_14bps"],
        "non_positive_net_after_14bps_count": (
            gross_audit["reconciliation"]["expected_evaluated"]
            - gross_audit["reconciliation"]["survived_above_14bps"]
        ),
        "survival_rate_of_all_evaluated": (
            gross_audit["reconciliation"]["survived_above_14bps"]
            / gross_audit["reconciliation"]["expected_evaluated"]
        ),
        "survival_rate_of_gross_wins": (
            gross_audit["reconciliation"]["survival_rate_of_gross_wins"]
        ),
        "folds": [
            {
                "fold_index": row["fold_index"],
                "evaluated": row["evaluated"],
                "gross_above_14bps": row["above_14bps"],
                "positive_net_after_14bps_count": row["survived_above_14bps"],
                "survival_rate_of_gross_wins": row["survival_rate_of_gross_wins"],
            }
            for row in gross_audit["folds"]
        ],
    }

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
        "gross_return_audit": gross_audit,
        "net_survival_14bps": net_survival,
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
