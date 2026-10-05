# Effective Evidence Protocol v1 — PRE-REGISTERED
Status: research-only, fail-closed.

## Purpose
Translate the locked Winner populations into a conservative effective-evidence quantity using only already-established dependence diagnostics.

## Locked inputs
- Prior Winner/Survivor population: 14
- Current Winner population: 28
- Cluster thresholds: exactly 0.5, 1.0, 1.5, 2.0
- Effective cluster count: N² / sum(cluster_size²)
- No threshold selection as a winner.

## Primary conservative quantity
For each population and each fixed threshold, report the effective cluster count.
For the primary conservative bound, use the minimum effective cluster count across the fixed sensitivity set.

This is a conservative dependence-adjusted evidence proxy, not a statistical effective sample size estimator.

## Combined evidence
Report:
- raw combined N = 42
- raw sum of the two population-level conservative effective counts
- conservative combined effective-evidence proxy = minimum-threshold effective count(prior) + minimum-threshold effective count(current)

The proxy is deliberately not treated as 42 independent observations.

## Claim boundary
This quantity does NOT prove statistical independence, predictive validity, causality, market generalization, or promotion eligibility. It does not justify deleting, weighting, selecting, or tuning observations. Promotion remains BLOCKED.
