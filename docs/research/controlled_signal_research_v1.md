# Controlled Signal Research v1

## Purpose
Research-only candidate specification on the frozen 8-fold OOS snapshot. This document defines a deterministic candidate before outcome inspection and does not create a production signal.

## Frozen evaluation contract
- Dataset: immutable 8-fold OOS snapshot already audited for outcome timestamp, embargo, fold independence, and winner-nearest-control boundary.
- Evaluation population: 1,049 observations.
- Label convention: Winner = net outcome above the pre-existing 14 bps boundary; Controls = all other eligible observations.
- No new rows may enter this study. The live collector is not an input.
- Snapshot provenance must be recorded by artifact/run identifier and content hash before execution.

## Candidate CSRv1-A
A descriptive directional-alignment candidate using only existing deterministic feature primitives:
1. EMA(20): close is above EMA20, or below EMA20.
2. Momentum(10): momentum value is positive, or negative.
3. Price/VWAP relation: close is above VWAP, or below VWAP.

A row is a candidate-positive only when all three directional relations agree:
- positive alignment: close > EMA20 AND momentum10 > 0 AND close > VWAP
- negative alignment: close < EMA20 AND momentum10 < 0 AND close < VWAP

Equality or missing inputs are candidate-negative/invalid, never coerced.

## Anti-overfitting locks
- No threshold search.
- No period search.
- No feature selection based on the 1,049 outcomes.
- No tuning on folds.
- No model fitting.
- No ranking, scoring, or optimization.
- No outcome-derived normalization.
- Feature values must be timestamped at or before the eligible observation boundary.

## Required audit outputs
For the frozen snapshot, report:
- candidate-positive count;
- Winner/Control counts within candidate-positive and candidate-negative populations;
- fold-by-fold candidate-positive counts;
- earliest/latest feature timestamps and outcome timestamps;
- leakage/embargo violations;
- missing/invalid feature counts;
- permutation/negative-control result if implemented.

These are descriptive research outputs, not a promotion decision.

## Gate
CSRv1-A may proceed only if provenance, temporal boundary, fold assignment, and deterministic feature definitions are all reproducible. Any failed integrity condition blocks interpretation of outcome separation.
