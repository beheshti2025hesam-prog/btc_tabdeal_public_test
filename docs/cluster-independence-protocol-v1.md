# Cluster / Independence Protocol v1 — PRE-REGISTERED
Status: research-only, fail-closed.
Purpose: estimate dependence without outcome-driven tuning.

## Locked metric
Use standardized Euclidean distance across the five locked numeric features:
ema_distance_pct, vwap_distance_pct, buy_ratio, buy_sell_delta, trade_count.

Standardization parameters MUST be computed from the frozen combined Winner+Control population before any cluster labels are inspected.

## Locked thresholds
Do not choose thresholds from observed cluster sizes. Report sensitivity at exactly:
0.5, 1.0, 1.5, 2.0 standardized-distance units.

## Cluster rule
Two observations are connected when distance <= threshold. Clusters are connected components of this graph.

## Independence reporting
For each threshold report:
- number of Winner clusters
- largest Winner cluster
- effective cluster count = sum(cluster sizes^2)^-1 scaled by N^2 (inverse concentration)
- Winner/Control cluster overlap descriptive only
- fold concentration inside clusters
- direction and regime concentration inside clusters

No threshold may be promoted as "the" threshold.

## Claim boundary
This is a dependence diagnostic, NOT proof of statistical independence, predictive validity, causality, or market generalization.
No data deletion, selection, tuning, or promotion is permitted.
Final promotion remains blocked.
