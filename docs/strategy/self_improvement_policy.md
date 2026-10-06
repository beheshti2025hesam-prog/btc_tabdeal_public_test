# HES Self-Improvement Policy

## Objective

The learning loop improves **decision quality**, not signal volume.

It may discover recurring failure patterns from completed trades and NO-TRADE
decisions. It must never silently rewrite the live strategy.

## Closed-loop architecture

Raw outcome
→ attribution
→ recurring failure pattern
→ improvement proposal
→ new candidate policy
→ untouched walk-forward/OOS evaluation
→ risk/regression checks
→ explicit promotion approval
→ immutable versioned policy

## Hard safety rules

1. No automatic threshold tuning on the evaluation set.
2. No training on future OOS outcomes before the OOS verdict is frozen.
3. No deletion or relabeling of losing records.
4. No winner reselection to make a candidate look better.
5. No automatic promotion from backtest/in-sample performance.
6. Any uncertainty in required evidence remains NO TRADE.
7. Every promoted policy gets a new version and a reproducible artifact/hash.
8. Rollback must be possible to the last accepted policy.
9. Signal count is never an optimization target by itself.
10. Quality improvement must survive direction, regime, and fold checks.

## What the agent is allowed to learn

- Which evidence families repeatedly precede losses.
- Which regimes create unstable decisions.
- Which direction/regime combinations need stronger confirmation.
- Which rejection reasons are disproportionately associated with later
  counterfactual failures.
- Whether a proposed feature improves robustness without increasing risk.

## What the agent is not allowed to do

- "Find" a threshold that maximizes historical win rate and immediately deploy it.
- Remove inconvenient losses.
- Reclassify outcomes after seeing the result.
- Use the same data both to discover and certify a change.
- Trade more often merely to improve coverage.

## Promotion contract

A candidate is promotable only when:

- OOS evaluation is complete.
- OOS data is independent from the proposal-generation sample.
- The candidate improves the quality objective.
- There is no material risk regression.
- The change is explicitly approved.
- A new immutable policy/version artifact is recorded.

The target remains high precision and selective trading. Near-100% win rate is an
aspiration, never a guaranteed property of the system.
