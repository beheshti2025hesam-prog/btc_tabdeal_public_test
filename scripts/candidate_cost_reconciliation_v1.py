#!/usr/bin/env python3
"""Reconcile fresh candidate walk-forward population with the frozen cost matrix.

Research-only: deterministic comparison, no tuning, fitting, ranking, promotion,
capital mutation, or execution.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CANDIDATE = Path("14_vs_1035_contrast_audit.json")
COST = Path("fresh_oos_cost_matrix_evidence.json")
OUT = Path("candidate_cost_reconciliation_v1.json")
CSV = "/tmp/hes_fresh_trades.csv"

EXPECTED_SCENARIOS = {
    (0.0, 0.0),
    (5.0, 2.0),
    (10.0, 5.0),
}
TOL = 1e-12


def close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL


def main() -> None:
    if not Path(CSV).is_file():
        raise SystemExit("FAIL: exact fresh snapshot is not materialized")

    subprocess.run(
        [
            "python",
            "scripts/run_real_oos_cost_matrix.py",
            "--csv",
            CSV,
            "--output",
            str(COST),
        ],
        check=True,
    )

    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    cost = json.loads(COST.read_text(encoding="utf-8"))

    candidate_protocol = candidate["protocol"]
    candidate_population = candidate["population"]
    candidate_folds = {x["fold_index"]: x for x in candidate["folds"]}
    matrix = cost["cost_matrix"]
    aggregate = matrix["aggregate"]
    measurements = matrix["measurements"]

    scenarios = {
        (
            float(x["transaction_cost_bps_per_side"]),
            float(x["slippage_bps_per_side"]),
        )
        for x in aggregate
    }
    assert scenarios == EXPECTED_SCENARIOS, scenarios
    assert len(candidate_folds) == 8
    assert len(measurements) == 8 * len(EXPECTED_SCENARIOS)

    # The zero-cost matrix must be the same gross walk-forward population
    # represented by the candidate contrast audit, fold by fold.
    zero = {
        int(x["fold_index"]): x
        for x in measurements
        if float(x["transaction_cost_bps_per_side"]) == 0.0
        and float(x["slippage_bps_per_side"]) == 0.0
    }
    assert len(zero) == 8

    fold_checks = []
    for fold_index in range(8):
        c = candidate_folds[fold_index]
        z = zero[fold_index]
        assert c["evaluated"] == z["evaluated"]
        assert c["wins"] == z["wins"]
        assert c["losses"] == z["losses"]
        assert close(float(c["gross_return"]), float(z["total_net_return"]))
        fold_checks.append(
            {
                "fold_index": fold_index,
                "evaluated": c["evaluated"],
                "wins": c["wins"],
                "losses": c["losses"],
                "gross_return_candidate": c["gross_return"],
                "zero_cost_matrix_return": z["total_net_return"],
                "match": True,
            }
        )

    candidate_eval = int(candidate_population["evaluated_oos"])
    matrix_eval = int(cost["walk_forward"]["evaluated"])
    assert candidate_eval == matrix_eval == sum(x["evaluated"] for x in zero.values())

    aggregate_checks = []
    for row in aggregate:
        scenario = (
            float(row["transaction_cost_bps_per_side"]),
            float(row["slippage_bps_per_side"]),
        )
        aggregate_checks.append(
            {
                "transaction_cost_bps_per_side": scenario[0],
                "slippage_bps_per_side": scenario[1],
                "evaluated": row["evaluated"],
                "wins": row["wins"],
                "losses": row["losses"],
                "total_net_return": row["total_net_return"],
            }
        )

    result = {
        "status": "CANDIDATE_COST_RECONCILIATION_PASS",
        "lineage": {
            "snapshot_data_blob_sha": candidate_protocol["snapshot_data_blob_sha"],
            "snapshot_source_commit": candidate_protocol["snapshot_source_commit"],
        },
        "population": {
            "candidate_evaluated_oos": candidate_eval,
            "cost_matrix_evaluated_oos": matrix_eval,
            "match": True,
        },
        "fold_reconciliation": fold_checks,
        "cost_scenarios": aggregate_checks,
        "safety": {
            "threshold_tuning": False,
            "model_fitting": False,
            "ranking_optimization": False,
            "capital_mutation": False,
            "promotion": False,
            "live_execution": False,
        },
        "claim_boundary": "descriptive research evidence only; not Signal validation or production authorization",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
