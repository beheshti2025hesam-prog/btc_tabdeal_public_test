#!/usr/bin/env python3
"""Embargo-adjusted fold/regime independence audit for the frozen BTC/USDT OOS snapshot.

Evidence-only. Re-runs the immutable real-data snapshot with the minimum
1-observation embargo required by the prior outcome-timestamp audit, then
treats temporal test folds as the independence unit. No threshold tuning,
parameter fitting, Signal construction, live execution, or promotion.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.real_data import RealDataBacktest
from core.strategy.baseline import BaselineDecision
from core.risk.boundary import RiskDecision

ROOT = Path(__file__).resolve().parents[1]
CSV = Path(os.environ.get("HES_FROZEN_CSV", str(ROOT / "data" / "trades.csv")))
OUTPUT = ROOT / "embargo_adjusted_fold_regime_independence.json"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534

TRAIN = 800
TEST = 400
STEP = 400
FOLDS = 8
EMBARGO = 1
THRESHOLD = 0.0014
OUTCOME_DELTA_SECONDS = 60

E0_WINNERS = 14
E0_CONTROLS = 1035
E0_FOLD_WINNERS = {0: 2, 1: 3, 2: 2, 3: 7, 4: 0, 5: 0, 6: 0, 7: 0}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def gross_return(sample) -> float | None:
    if sample.entry_price is None or sample.exit_price is None:
        return None
    if sample.decision.value == "LONG":
        return (sample.exit_price - sample.entry_price) / sample.entry_price
    if sample.decision.value == "SHORT":
        return (sample.entry_price - sample.exit_price) / sample.entry_price
    return None


def kish_ess(cluster_sizes: list[int]) -> float:
    total = sum(cluster_sizes)
    denom = sum(x * x for x in cluster_sizes)
    return (total * total / denom) if denom else 0.0


def main() -> None:
    actual_blob = git_blob_sha(CSV)
    assert actual_blob == EXPECTED_BLOB, (actual_blob, EXPECTED_BLOB)

    backtest = RealDataBacktest(csv_path=str(CSV))
    wf = backtest.run_walk_forward(
        train_size=TRAIN,
        test_size=TEST,
        step_size=STEP,
        embargo_size=EMBARGO,
    )
    observations = backtest._last_observations
    folds_to_audit = wf.folds[:FOLDS]
    assert len(folds_to_audit) == FOLDS, len(folds_to_audit)

    rows = []
    folds = []
    for fold in folds_to_audit:
        evaluated = []
        test_start = TRAIN + EMBARGO + fold.index * STEP
        test_observations = observations[test_start:test_start + TEST]
        assert len(test_observations) == TEST, len(test_observations)
        for observation in test_observations:
            sample = observation.sample
            g = gross_return(sample)
            if g is None:
                continue
            evaluated.append({
                "timestamp": sample.timestamp.isoformat(),
                "direction": sample.decision.value,
                "gross_return": g,
            })

        total_gross = sum(r["gross_return"] for r in evaluated)
        regime = "uptrend" if total_gross >= 0.01 else "downtrend" if total_gross <= -0.01 else "range"
        winners = [r for r in evaluated if r["gross_return"] > THRESHOLD]
        controls = [r for r in evaluated if r["gross_return"] <= THRESHOLD]

        folds.append({
            "fold_index": fold.index,
            "train_start": fold.train_start.isoformat(),
            "train_end": fold.train_end.isoformat(),
            "test_start": fold.test_start.isoformat(),
            "test_end": fold.test_end.isoformat(),
            "train_observations": fold.train_observations,
            "test_observations": fold.test_observations,
            "evaluated": len(evaluated),
            "gross_return_sum": total_gross,
            "regime": regime,
            "winner_count": len(winners),
            "control_count": len(controls),
            "first_test_outcome_timestamp": (
                fold.test_samples[0].timestamp.isoformat()
                if fold.test_samples else None
            ),
        })

        for r in winners:
            rows.append({
                **r,
                "fold_index": fold.index,
                "fold_regime": regime,
                "outcome_timestamp": r["timestamp"],
            })

    evaluated = sum(f["evaluated"] for f in folds)
    winners = [r for r in rows]
    controls = evaluated - len(winners)

    fold_winners = {f: sum(r["fold_index"] == f for r in winners) for f in range(FOLDS)}
    fold_controls = {
        f: next(x["control_count"] for x in folds if x["fold_index"] == f)
        for f in range(FOLDS)
    }
    supported_folds = [f for f, n in fold_winners.items() if n > 0]
    cluster_sizes = [fold_winners[f] for f in supported_folds]
    winner_ess = kish_ess(cluster_sizes)

    regime_winners = Counter(r["fold_regime"] for r in winners)
    direction_winners = Counter(r["direction"] for r in winners)

    # Leave-one-fold-out descriptive survival. The excluded fold is never used
    # to choose a threshold or strategy; the threshold is the frozen 14bps cost
    # boundary inherited from the prior evidence layer.
    loo = []
    for excluded in range(FOLDS):
        remaining = [r for r in winners if r["fold_index"] != excluded]
        loo.append({
            "excluded_fold": excluded,
            "winner_count_removed": fold_winners[excluded],
            "winner_count_remaining": len(remaining),
            "winner_supported_folds_remaining": len({
                r["fold_index"] for r in remaining
            }),
            "remaining_winner_gross_sum": sum(r["gross_return"] for r in remaining),
        })

    # Compare only the immutable winner population counts, not performance
    # rankings. This makes the embargo effect explicit without reinterpreting e0.
    e0_supported = sum(1 for n in E0_FOLD_WINNERS.values() if n > 0)
    e0_ess = kish_ess([n for n in E0_FOLD_WINNERS.values() if n > 0])

    result = {
        "status": "evidence-only",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "current_data_blob_sha_verified": actual_blob,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
        },
        "protocol": {
            "train": TRAIN,
            "test": TEST,
            "step": STEP,
            "folds": FOLDS,
            "historical_embargo_observations_e0": 0,
            "embargo_adjusted_observations": EMBARGO,
            "embargo_seconds_for_next_1m_outcome": OUTCOME_DELTA_SECONDS,
            "gross_winner_threshold": THRESHOLD,
            "threshold_source": "frozen prior evidence; not tuned here",
        },
        "e0_baseline": {
            "evaluated_oos": E0_WINNERS + E0_CONTROLS,
            "winners": E0_WINNERS,
            "controls": E0_CONTROLS,
            "winner_counts_by_fold": {str(k): v for k, v in E0_FOLD_WINNERS.items()},
            "winner_supported_fold_count": e0_supported,
            "winner_kish_ess": e0_ess,
        },
        "embargo_adjusted_population": {
            "evaluated_oos": evaluated,
            "winners_gt_14bps": len(winners),
            "controls_le_14bps": controls,
            "reconciles": len(winners) + controls == evaluated,
        },
        "folds": folds,
        "fold_independence": {
            "independence_unit": "embargo-adjusted walk_forward_test_fold",
            "supported_fold_indices": supported_folds,
            "supported_fold_count": len(supported_folds),
            "support_fraction": len(supported_folds) / FOLDS,
            "winner_counts_by_fold": {str(k): v for k, v in fold_winners.items()},
            "control_counts_by_fold": {str(k): v for k, v in fold_controls.items()},
            "winner_kish_effective_sample_size": winner_ess,
            "largest_winner_fold_share": (
                max(cluster_sizes) / len(winners) if winners else 0.0
            ),
        },
        "regime_independence": {
            "winner_counts_by_regime": dict(regime_winners),
            "winner_counts_by_direction": dict(direction_winners),
            "regime_supported_by_winners": sorted(regime_winners),
            "note": "Regime is a descriptive fold partition; it is not a selection variable.",
        },
        "leave_one_fold_out": loo,
        "outcome_embargo_boundary": {
            "minimum_embargo_observations": 1,
            "minimum_embargo_seconds": 60,
            "e0_cross_boundary_status": "CROSS_BOUNDARY_OUTCOME",
            "adjusted_protocol_status": "OUTCOME_SEPARATED_BY_ONE_OBSERVATION",
        },
        "claim_boundary": {
            "signal_created": False,
            "threshold_tuned": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
            "interpretation": (
                "Embargo adjustment changes the temporal partition for descriptive "
                "evidence. The temporal test fold remains the independence unit; "
                "nominal winner rows are not treated as independent confirmations."
            ),
        },
    }

    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "evaluated_oos": evaluated,
        "winners_gt_14bps": len(winners),
        "controls_le_14bps": controls,
        "winner_supported_folds": supported_folds,
        "winner_ess": winner_ess,
        "winner_counts_by_fold": fold_winners,
        "winner_counts_by_regime": dict(regime_winners),
    }, indent=2))


if __name__ == "__main__":
    main()
