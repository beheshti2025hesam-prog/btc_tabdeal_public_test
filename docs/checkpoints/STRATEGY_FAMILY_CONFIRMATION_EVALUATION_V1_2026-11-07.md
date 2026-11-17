# HES Trade Agent — Strategy-Family Confirmation & Evaluation Contracts v1

**Date:** 2026-11-07
**Branch:** `feat/strategy-family-confirmation-v1`
**Base:** `f5d505567522555ee1be9c260e83085347515721` (current `main`)
**Disposition:** ISOLATED CONTRACT IMPLEMENTATION / NOT WIRED INTO ACTIVE DECISION PIPELINE / NO STRATEGY ACTIVATION.

## Objective

Add the missing family-specific confirmation and evaluation contracts without rebuilding the existing Gate.io data path, family router, provenance envelope, journal, confirmation engine, or Risk Gate. Preserve the current Trend behavior and make the Range confirmation path structurally independent while keeping it research-only.

## Added components

- `forward/strategy_family_confirmation_v1.py`
  - Trend delegates to the existing `ConfirmationPolicyV1` unchanged (three required checks).
  - Range has its own eight-check contract: candidate validity, persistent RANGE evidence, boundary location, reversal trigger, direction/regime alignment, directional flow confirmation, structure confirmation, and cost-adjusted geometry.
  - Both paths require exact family/version/source/symbol/timeframe/regime/direction/time binding, a valid candidate evidence digest, and contemporaneous PASS evidence.
  - Range returns `RESEARCH_CONFIRMED_LONG/SHORT`, never the `CONFIRMED_LONG/SHORT` state accepted by the shared Risk Gate. The Risk Gate remains the common independent veto.
  - Every result explicitly carries `confirmation_authority=false`, `candidate_generation_authorized=false`, `execution_enabled=false`, and `orders_placed=false`.
- `forward/strategy_family_evaluation_v1.py`
  - Requires separate, non-overlapping Trend and Range family cohorts; mixed family IDs or reused cohort IDs fail closed.
  - Requires >=100 eligible resolved outcomes per family, strict win rate >90% (exactly 90% fails), positive net expectancy after costs, profit factor >1, valid drawdown reporting, verified fee/slippage evidence, and >=100 independently evidenced OOS outcomes per family with the same strict performance requirements.
  - Validates upstream report status, report and OOS hashes, outcome-count arithmetic, win-rate arithmetic, and cost-model hashes; malformed check/report payloads fail closed.
  - Combines daily actionable counts across both families and enforces one global maximum of three per UTC day; it is a cap, not a quota.
  - A performance PASS never authorizes strategy activation, candidate generation, risk approval, or execution. The Range family remains `RESEARCH_ONLY_NOT_ACTIVE`.
- New deterministic tests in `tests/strategy/test_strategy_family_confirmation_v1.py` and `tests/strategy/test_strategy_family_evaluation_v1.py`.

## Safety / non-goals

- No change to Gate.io Public Spot BTC_USDT or `global_market_data_reader_v1`; 15m remains setup authority and 1m remains downstream entry refinement.
- No change to the common Risk Gate, current 3R check, position sizing, leverage, stop/target rules, execution venue, or execution adapter.
- No Range candidate generator is activated. The previously tested Range prototypes remain unapproved; a research-confirmation PASS is not a trade signal.
- No changes to the active service, dashboard, data/journal files, release pointer, credentials, exchange accounts, or real-order path.
- This PR adds independent family contracts only. Pipeline dispatch, actual Range setup generation, journal integration of family-specific outcome cohorts, and independent raw-ledger evaluation remain later gated integration work. Do not claim the full family architecture is complete from this PR alone.

## Verification

- Focused new tests: **21 passed** with warnings treated as errors.
- Full repository test suite on this branch: **1,197 passed, 82 subtests passed in 11.39s**, warnings treated as errors.
- `git diff --check`: passed.
- Base is exactly current `main` at the start of this work; work occurred in a separate Git worktree so the sole VPS root checkout and its 372 pre-existing dirty/untracked entries were not touched.

## Next gates

1. Wire family dispatch in the existing `strategy_gate_pipeline_v1` without changing Trend outputs; add exact replay-equivalence tests.
2. Build a separately preregistered Range setup evaluator from validated 15m range evidence; 1m may refine an already validated setup only.
3. Bind each family to append-only, provenance-bound journal cohorts and raw-outcome readers; do not reuse one family’s outcomes for another.
4. Keep current 3R Risk Gate floor and all common risk controls unchanged until separate evidence review and explicit policy approval. No family-specific exception may weaken the global Risk Gate.
5. Run chronological walk-forward and independent OOS on verified costs; at least 100 resolved eligible trades per family and >90% in both cohorts are acceptance targets, not promises.
6. Keep the global three-signal daily ceiling, paper-only mode, and explicit user authorization requirement.

**Decision:** safe family-specific confirmation/evaluation contracts are now available for review; runtime wiring and Range strategy acceptance remain OPEN; live execution stays OFF.


## Second-pass hardening

- Candidate confirmation now requires canonical Gate.io source binding, a valid evidence SHA-256, exact canonical symbol/timeframe, and non-empty contemporaneous evidence references.
- The family evaluator now requires the upstream family report itself to be PASS, and malformed check objects or cost-model hashes fail closed.
- Final isolated-worktree verification after these corrections: **21 focused tests passed; 1,197 full-suite tests passed + 82 subtests**, warnings treated as errors; `git diff --check` passed.