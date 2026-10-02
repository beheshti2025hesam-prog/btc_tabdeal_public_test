# HES Trade Agent — Downstream Impact Audit for Locked 1049 v1

## Purpose
Determine whether the locked Fold-7 raw-time gap changes downstream OOS evidence without modifying the 1,049 frozen evaluator population.

## Finding
The gap affects raw time coverage, but excluded evaluator observations = 0 and observation coverage Δ = 0.0%. Fold 7 remains 134 evaluated observations. Therefore the locked observation-level OOS metrics do not require recomputation because of this gap.

This does not establish that no raw market data was lost.

## Fold-level gross impact
Frozen gross fold returns:
- Fold 0: +0.003715
- Fold 1: +0.003387
- Fold 2: +0.007373
- Fold 3: +0.014016
- Fold 4: -0.003366
- Fold 5: +0.005769
- Fold 6: -0.000777
- Fold 7: -0.002277

Five of eight folds are positive before explicit execution-cost assumptions. Fold 7 is already slightly negative at gross level.

## Cost / slippage impact
The frozen cost boundary uses the same 1,049 evaluated observations:
- 0/0 bps per side: +0.027840 aggregate, 528 wins / 479 losses.
- 5/2 bps per side: -1.440760 aggregate, 14 wins / 1,035 losses.
- 10/5 bps per side: -3.119160 aggregate, 1 win / 1,048 losses.

At a 14 bps round-trip adverse-cost boundary, 14 / 1,049 = 1.3346% of evaluated observations remain positive. All eight fold-level aggregates are negative under the 5 bps fee + 2 bps slippage-per-side scenario.

## Interpretation boundary
1. Gap → locked OOS metrics: no measured population impact; observation Δ = 0.
2. Gap → raw temporal coverage: material; Fold 7 contains a 5.2263508333-hour raw-time coverage condition.
3. Gap → cost sensitivity: the locked population remains strongly cost-sensitive under the explicit scenarios.
4. Gap → promotion: this audit does not strengthen a promotion case and does not authorize live execution.
5. Raw-data loss claim: not established by this audit.

## Safety
- main is not modified by this audit.
- data-engine-v1 remains untouched.
- The 1,049 Evidence Lock remains immutable.
- No synthetic fill, replacement row, or causal reassignment is introduced.
- Live execution and promotion remain disabled.

## References
- Formal Evidence Lock: PR #129, immutable workflow Run 181, artifact #11162212837.
- Frozen OOS cost/slippage boundary: PR #86, protocol oos-real-btcusdt-v1-800x400x400-e0.
