# HES Trade Agent — Forward Start

## Status
FORWARD_ONLY

## Forward Start
2026-10-07

## Purpose
This marker defines the operational boundary for the new forward-only development and evaluation path.

## Historical Boundary
All pre-existing historical analysis, including prior Winner/Survivor populations and historical failure-performance analysis, is archival context only. It must not be used as an optimization target, threshold-tuning basis, feature-selection basis, or future decision rule.

## Forward Rules
- No historical Winner/Survivor reselection.
- No threshold tuning from historical outcomes.
- No feature selection from historical outcomes.
- No deletion or rewriting of historical records.
- Fresh forward observations are the basis for future evaluation.
- NO_TRADE is a valid forward decision and must be recorded.
- Any future strategy change requires evidence generated from the new forward period, not the archived historical population.

## Operational Chain
Fresh Data -> Signal -> Confirmation -> Risk -> LONG/SHORT/NO_TRADE -> Forward Journal -> Forward Evaluation -> Learning

## Baseline Principle
Past = Archive. Future = Evidence.

## Scope
This marker does not claim that the current strategy is profitable or production-ready. It establishes only the boundary and protocol for forward evaluation.


## Immutable provenance pin — 2026-10-19

- **Forward-boundary marker introduction commit:** `d2c24c5b5c1248f1ee422ccb4717e78a466a34e0` ([GitHub commit](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/commit/d2c24c5b5c1248f1ee422ccb4717e78a466a34e0)). This is the commit that introduced this marker and the initial forward contracts on 2026-10-07.
- **Operational baseline policy commit:** `7aea2154cf91e2237c76de734389ed22551dfd22` ([GitHub commit](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/commit/7aea2154cf91e2237c76de734389ed22551dfd22)). It establishes the no-retroactive-repair and no-live-execution policy.
- The marker date is a policy boundary, **not proof** that a live forward runtime or complete opportunity journal was running on that date. At the current `main` commit, `forward/runtime_config_v1.json` still says `FORWARD_RUN_PENDING`, `NOT_CONFIGURED`, and `live_execution_enabled=false`; the journal schema is `CONTRACT_ONLY`.
- Do not rewrite the original boundary date or backfill decisions/outcomes. Before starting a new operational run, separately pin the exact runtime code/config commit, policy/ruleset versions, observation source, and journal path; keep all decisions including `NO_TRADE`. Until that run is explicitly configured and validated, this document does not authorize a collector launch, deployment, or trading.
