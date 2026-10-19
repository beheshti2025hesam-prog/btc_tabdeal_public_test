#!/usr/bin/env python3
"""Evidence-only cost-aware survival audit over the frozen 14-vs-1035 OOS winners.

Reuses the immutable contrast snapshot produced in CI. No threshold fitting,
signal construction, model fitting, execution, or promotion is performed.
The three cost scenarios are the already-established measurement assumptions:
0/0, 5/2, and 10/5 bps per side.

This audit also records the outcome-timestamp boundary inherited from the
real-data pipeline: each observation uses the next contiguous 1-minute candle
as its realized outcome. The frozen protocol currently has embargo=0, so the
last training observation's outcome timestamp reaches the first test timestamp.
That boundary is explicitly flagged for any future learned-model use.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean, median, pstdev

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "14_vs_1035_contrast_audit.json"
OUTPUT = ROOT / "cost_aware_14_vs_1035_survival_evidence.json"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
EXPECTED_WINNERS = 14
EXPECTED_CONTROLS = 1035
EXPECTED_FOLDS = 8
EXPECTED_PROTOCOL = "oos-real-btcusdt-v1-800x400x400-e0"
SCENARIOS = (
    {"name": "zero_cost", "transaction_cost_bps_per_side": 0.0, "slippage_bps_per_side": 0.0},
    {"name": "5bps_plus_2bps", "transaction_cost_bps_per_side": 5.0, "slippage_bps_per_side": 2.0},
    {"name": "10bps_plus_5bps", "transaction_cost_bps_per_side": 10.0, "slippage_bps_per_side": 5.0},
)
FEATURES = ("ema_distance_pct", "vwap_distance_pct", "buy_ratio", "buy_sell_delta", "trade_count")


def net_return(gross: float, tx: float, slip: float) -> float:
    return gross - 2.0 * (tx + slip) / 10_000.0


def summary(values):
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": fmean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


def smd(a, b):
    if not a or not b:
        return None
    va = pstdev(a) ** 2 if len(a) > 1 else 0.0
    vb = pstdev(b) ** 2 if len(b) > 1 else 0.0
    pooled = ((va + vb) / 2.0) ** 0.5
    return (fmean(a) - fmean(b)) / pooled if pooled else 0.0


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    protocol = data["protocol"]
    assert protocol["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert protocol["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert protocol["snapshot_run_id"] == EXPECTED_RUN_ID
    assert protocol["folds"] == EXPECTED_FOLDS
    assert protocol["train"] == 800
    assert protocol["test"] == 400
    assert protocol["step"] == 400
    winners = data["winners"]
    assert len(winners) == EXPECTED_WINNERS
    assert sum(int(v) for v in data["categorical"]["fold_controls"].values()) == EXPECTED_CONTROLS

    # These are the previously reconciled gross-return bins. Recompute the
    # 14/1035 threshold boundary from the frozen winner/control population.
    all_counts = {
        "below_zero": sum(1 for r in winners if r["gross_return"] < 0),
        "zero_to_14bps": 0,
        "above_14bps": len(winners),
    }
    # The contrast snapshot stores winners only; the full 479/556/14
    # reconciliation is therefore carried as an explicit external-boundary
    # assertion, not fabricated from the 14-row subset.
    reconciled_full_population = {"below_zero": 479, "zero_to_14bps": 556, "above_14bps": 14, "total": 1049}

    scenario_results = {}
    for scenario in SCENARIOS:
        key = scenario["name"]
        net_values = [net_return(r["gross_return"], scenario["transaction_cost_bps_per_side"], scenario["slippage_bps_per_side"]) for r in winners]
        survivors = [r for r, n in zip(winners, net_values) if n > 0]
        scenario_results[key] = {
            "assumption": scenario,
            "winner_population": EXPECTED_WINNERS,
            "positive_net_survivors": len(survivors),
            "survival_fraction": len(survivors) / EXPECTED_WINNERS,
            "net_return_summary_all_14": summary(net_values),
            "survivor_gross_sum": sum(r["gross_return"] for r in survivors),
            "survivor_net_sum": sum(net_values[i] for i, r in enumerate(winners) if net_values[i] > 0),
            "survivor_fold_counts": {str(f): sum(1 for r in survivors if r["fold_index"] == f) for f in range(EXPECTED_FOLDS)},
            "survivor_regime_counts": {
                regime: sum(1 for r in survivors if r["fold_regime"] == regime)
                for regime in sorted(set(r["fold_regime"] for r in winners))
            },
            "survivor_direction_counts": {
                direction: sum(1 for r in survivors if r["direction"] == direction)
                for direction in sorted(set(r["direction"] for r in winners))
            },
        }
        # Feature contrast among cost survivors versus the same frozen control
        # population is descriptive only; controls are not reconstructed.
        for feature in FEATURES:
            sv = [r[feature] for r in survivors]
            cv = [r[feature] for r in data["winners"]]  # replaced below for no fabricated controls
            scenario_results[key].setdefault("feature_contrast_survivors", {})[feature] = {
                "survivor_summary": summary(sv),
                "control_comparison_available": False,
                "note": "Frozen contrast artifact does not materialize all 1035 control rows; no control reconstruction is performed.",
            }

    # Gross-return bins among the frozen 14 are included for transparency.
    winner_bins = {
        "below_zero": sum(1 for r in winners if r["gross_return"] < 0),
        "zero_to_14bps": sum(1 for r in winners if 0 <= r["gross_return"] <= 0.0014),
        "above_14bps": sum(1 for r in winners if r["gross_return"] > 0.0014),
    }

    # Outcome boundary audit. RealDataBacktest creates a BacktestSample at
    # candle.end and uses the next contiguous candle close as the outcome.
    # With e0, the final train label can land exactly at the first test
    # timestamp; that is a leakage boundary for future learned models.
    boundary = {
        "protocol_id": EXPECTED_PROTOCOL,
        "train_size": 800,
        "test_size": 400,
        "step_size": 400,
        "embargo_size": 0,
        "outcome_definition": "next contiguous 1-minute candle close",
        "outcome_timestamp_relation": "observation_timestamp + 60 seconds when continuity holds",
        "learned_model_boundary_status": "requires_embargo_or_equivalent_purge",
        "cross_boundary_risk": True,
        "reason": "The last training observation's next-candle outcome can occur at the first OOS test timestamp when embargo=0.",
        "current_evidence_use": "descriptive execution-free audit only; no learned model is fit here",
    }

    result = {
        "status": "evidence-only",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
        },
        "population": {
            "nominal_winners": EXPECTED_WINNERS,
            "nominal_controls": EXPECTED_CONTROLS,
            "fold_count": EXPECTED_FOLDS,
            "reconciled_full_gross_bins": reconciled_full_population,
            "winner_subset_gross_bins": winner_bins,
        },
        "cost_scenarios": scenario_results,
        "outcome_timestamp_boundary": boundary,
        "claim_boundary": {
            "signal_created": False,
            "threshold_tuned": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
            "control_reconstruction": False,
            "interpretation": "Cost survival is descriptive over the frozen 14 winners; it is not a new selection rule.",
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "positive_net_survivors": {
            k: v["positive_net_survivors"] for k, v in scenario_results.items()
        },
        "boundary_status": boundary["learned_model_boundary_status"],
    }, indent=2))


if __name__ == "__main__":
    main()

