# HES Trade Agent — Signal Construction Research v1

status: research-only
purpose: deterministic construction and evaluation of the pre-registered candidate family on a fresh, lineage-locked snapshot.

## Hard boundary

This protocol does not create a production Signal and does not authorize promotion or live execution.

Forbidden:
- threshold tuning or threshold search
- period search
- model fitting
- ranking/scoring optimization
- outcome-derived normalization
- selection using evaluation outcomes
- random shuffle or cross-fold leakage
- synthesis across timestamp gaps
- live collector input
- order generation or execution
- capital mutation
- wallet conversion, withdrawal, or transfer

## Candidate definition

Candidate features are fixed to:
1. buy_ratio
2. buy_sell_delta
3. trade_count

The candidate family is inherited from the registered Controlled Candidate Performance Study v1 contract. No additional feature may be introduced in this gate.

The candidate definition must be deterministic and identical for every fold. Any threshold or rule used by the implementation must come from the already-registered candidate contract; this gate may not optimize it.

## Snapshot and population

The input must be an exact, immutable, lineage-locked fresh snapshot.

Population is snapshot-lineage-specific and means evaluated OOS observations produced by the fixed walk-forward construction. Population counts must be recomputed from the exact snapshot and are not transferable from another snapshot lineage.

Required fold shape:
- folds: 8
- train: 800
- test: 400
- step: 400

Preserve fixed fold boundaries. Do not synthesize observations across timestamp gaps.

## Temporal boundary

Every candidate feature value must use information available at or before the candidate timestamp.

The realized outcome must remain outside the feature construction boundary according to the registered embargo/timestamp protocol. No future outcome may influence candidate features, normalization, rule construction, or evaluation.

## Evaluation

Required:
- deterministic candidate construction
- 8-fold walk-forward evaluation
- fold-level results
- negative results retained
- cost/slippage matrix reconciliation
- timestamp and sequence integrity checks
- missing/invalid feature accounting
- leakage/embargo violation accounting
- reproducible snapshot lineage hashes

The evaluation must report:
- total evaluated OOS observations
- winner/control counts under the already-registered gross outcome convention
- per-fold evaluated counts
- per-fold candidate result
- fold survival/sign consistency
- cost/slippage results
- concentration and independence limitations

## Claim boundary

Allowed claim:
descriptive research evidence about a deterministic candidate construction on the exact locked snapshot.

Not allowed:
- predictive performance established
- production signal validated
- profitability guarantee
- promotion authorization
- live trading authorization

## Failure policy

Fail closed if:
- snapshot provenance cannot be reproduced
- fold boundaries differ
- feature construction is non-deterministic
- timestamp/sequence boundary fails
- leakage or embargo violation is detected
- unexpected features appear
- candidate parameters are tuned or searched
- population cannot be reconciled

A weak or negative result must be preserved as evidence and must not be rescued by tuning.

## Gate exit

A PASS permits only the next research/evidence review. It does not permit production Signal construction, promotion, live execution, or wallet operations.
