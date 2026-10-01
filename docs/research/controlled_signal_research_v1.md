# Controlled Signal Research v1

## Purpose
Research-only candidate specification on the fresh, independently bounded OOS snapshot. This document freezes the candidate definition before any candidate-performance interpretation. It does not create a production Signal.

## Frozen lineage
- Fresh snapshot source ref: `main`
- Fresh snapshot source commit: `86631f2522aa74a38cfa21fa28afe8d49fbc5f20`
- Fresh snapshot Git blob SHA: `b296b1c95f075518bea0b56fd11bbf5f0f613a04`
- Frozen prior boundary sequence: `38586238655`
- Frozen prior boundary timestamp: `2026-09-28T08:27:38.179Z`
- First independent record sequence: `38710284291`
- First independent record timestamp: `2026-09-28T19:08:56.951Z`
- Coverage gap: `38478.772` seconds (10h41m18.772s), explicitly recorded and never treated as continuity.
- Evaluation population inherited from the fixed evidence protocol: 1,049 OOS observations.
- Existing boundary: >14 bps gross/net convention inherited from prior evidence; no redefinition here.

## Candidate CANDIDATE_RESEARCH_V1
The candidate uses only the three features that survived the prior independence-adjusted evidence review as temporally sign-stable:

1. **Buy Ratio**
2. **Delta (Buy-Sell Delta)**
3. **Trade Count**

The candidate is a research input set, not a tuned numeric rule. No new numeric threshold is introduced here.

## Evidence inheritance
Prior evidence classifies:
- Buy Ratio: temporally sign-stable across all 8 Fold-LOO exclusions and all 14 Winner-LOO exclusions.
- Delta: temporally sign-stable across all 8 Fold-LOO exclusions and all 14 Winner-LOO exclusions.
- Trade Count: temporally sign-stable across all 8 Fold-LOO exclusions and all 14 Winner-LOO exclusions.
- EMA and VWAP: fold-sensitive and therefore excluded from this candidate definition.

Temporal fold is the independence unit. The 14 nominal winners are not treated as 14 independent confirmations; prior evidence measured Kish ESS ≈ 2.97 and winner support in 4 of 8 folds.

## Anti-overfitting and temporal locks
- No threshold search.
- No period search.
- No feature selection using evaluation outcomes beyond the already-registered evidence gate.
- No fold tuning.
- No model fitting.
- No ranking/scoring optimization.
- No outcome-derived normalization.
- Candidate inputs must use information available at or before the candidate timestamp.
- One-observation outcome separation from the E1 embargo boundary is retained.
- No random shuffle and no cross-fold leakage.
- No live collector input.
- No order generation, live execution, or promotion.

## Required candidate-study outputs
The execution-free study must report:
- evaluated OOS count;
- Winner/Control counts;
- feature-wise descriptive separation;
- temporal fold coverage;
- fold-level sign consistency;
- lineage hash/commit;
- timestamp and sequence integrity;
- leakage/embargo violations;
- missing/invalid feature counts;
- claim boundary flags.

The result is descriptive evidence only. It must not be represented as predictive performance or a production Signal.

## Gate
Interpretation is blocked if snapshot provenance, sequence/timestamp boundary, fold assignment, or deterministic feature construction is not reproducible.

## Explicit opening boundary
Controlled Signal Research v1 is now an **open research gate**, not a production gate:
- research: ON
- Signal construction for production: OFF
- promotion: OFF
- live execution: OFF
- data-engine-v1 integration: OFF
