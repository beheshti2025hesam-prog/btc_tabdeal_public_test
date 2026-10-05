# Candidate Definition Freeze Gate v1

status: research-only
decision: NOT_READY_FOR_SIGNAL_RULE

## Finding

The current evidence gate registers three research features:
- buy_ratio
- buy_sell_delta
- trade_count

The evidence establishes descriptive/temporal stability for these features. It does not register a deterministic LONG/SHORT decision rule, numeric thresholds, or a mapping from feature values to orders/signals.

The existing BaselineStrategy is not an acceptable substitute for this candidate definition because its decision logic depends on EMA and VWAP in addition to Buy Ratio, while EMA and VWAP were explicitly excluded from CANDIDATE_RESEARCH_V1. Reusing that strategy would therefore change the frozen candidate definition.

## Freeze rule

No Signal Construction Research implementation may invent:
- a new numeric threshold;
- a Delta threshold;
- a Trade Count threshold;
- a feature weighting;
- a confirmation count;
- a direction mapping;
- a score;
- a ranking rule.

Any such rule must first be registered as a separate deterministic research contract and frozen before evaluation.

## Allowed work before the next freeze

- deterministic feature construction audits;
- lineage and timestamp/sequence validation;
- descriptive feature distributions;
- missing/invalid feature audits;
- fold-level descriptive evidence;
- cost/slippage reconciliation of an already-registered rule.

## Prohibited work

- discovering a rule from the fresh evaluation outcomes;
- searching thresholds;
- testing multiple candidate rules and selecting one by outcome;
- fitting a classifier/model;
- optimizer/ranking;
- production Signal creation;
- promotion;
- live execution;
- wallet operations.

## Gate result

The laboratory is open, but the Signal-rule freeze gate is NOT READY.

The correct next action is to define and independently register a deterministic candidate rule without using the fresh evaluation outcomes. Until that happens, the system remains descriptive research only.
