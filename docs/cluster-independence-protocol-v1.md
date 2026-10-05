# Cluster / Independence Protocol v1 — PRE-REGISTERED
Status: research-only, fail-closed.

## Purpose
Estimate dependence/concentration among the locked Winner observations without outcome-driven tuning.

## Locked metric
Standardized Euclidean distance across the five locked numeric features:
ema_distance_pct, vwap_distance_pct, buy_ratio, buy_sell_delta, trade_count.

Standardization parameters are reconstructed from the frozen Winner+Control summary statistics already emitted by the locked protocol snapshot. Individual Control rows are not present in that snapshot artifact, so v1 does not claim Winner/Control cluster overlap.

## Locked thresholds
Sensitivity is reported at exactly: 0.5, 1.0, 1.5, 2.0 standardized-distance units.
No threshold is selected as the winner.

## Cluster rule
Two Winner observations are connected when distance <= threshold. Clusters are connected components of this graph.

## Independence reporting
For each threshold report:
- number of Winner clusters
- largest Winner cluster
- effective Winner cluster count = N^2 / sum(cluster_size^2)
- cluster size distribution
- descriptive concentration only

Direction, regime, and fold concentration remain separate audits; v1 does not combine them into a post-hoc clustering threshold.

## Claim boundary
This is a dependence/concentration diagnostic, NOT proof of statistical independence, predictive validity, causality, or market generalization.
No data deletion, selection, tuning, or promotion is permitted.
Final promotion remains blocked.
