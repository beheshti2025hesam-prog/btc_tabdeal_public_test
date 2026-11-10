# Strategy Family Intelligence — Implementation Plan

**Base:** PR #480 head 1f81f90897441c3501c802416ed300c4725de2d2  
**Isolation:** detached worktree /tmp/hes-strategy-intelligence-20261110; primary checkout untouched.

## Phase 0 — preserve and inventory
- [x] Capture approved architecture in Notion Master Checkpoint.
- [x] Confirm current router/context/confirmation/evaluation/paper cohort modules exist.
- [x] Confirm the primary checkout is dirty and must not be reset/cleaned.
- [x] Create isolated worktree from PR #480 head.
- [x] Map the existing router/context/confirmation/evaluation/paper cohort/journal/evidence modules; confirmed Range evidence builder and shared Trend evidence provider already exist and must be reused.
- [ ] Reconcile PR #480's independent review before treating it as a stable merge base. PR #491 is stacked on PR #480.

## Phase 1 — contracts and research dispatch
- [x] Add versioned four-family research assessment contract without changing the existing router.
- [x] Replace the synthetic feature-map prototype with an actual persisted Gate.io 15m OHLCV research assessor; four families are evaluated independently from the same hashed closed-candle window.
- [x] Keep candidate generation, confirmation, Risk, activation and execution false.
- [x] Add deterministic tests for canonical Gate.io scope, causal closed-candle features, regime/direction alignment, cost-adjusted invalidation geometry, 1m non-authority, fail-closed behavior and SHA-256 provenance binding.
- [x] Add the assessor as a diagnostic field to the existing gate pipeline; preserve Trend/Range candidate, confirmation, Risk and final decision paths unchanged.\n- [x] Run a read-only one-shot against the current persisted Gate.io 15m/1h/4h feeds; observed Trend Continuation research eligibility while final decision remained NO_TRADE.

## Phase 1 validation
- [x] Isolated full repository suite: 1,309 passed + 82 subtests.
- [x] Focused family, pipeline, journal, dashboard-data and learning-loop suite: 47 passed in the latest focused gate/journal/learning suite before final cost-floor/hash tests; full suite rerun required.
- [x] Exact-head GitHub CI: 32/32 successful on initial code commit 31323d92dee4e25e96cfec313b4f00721c8a7231; latest docs-only follow-up CI is pending.
- [ ] Independent review of PR #491.

## Phase 2 — family evaluators and journal
- [x] Reuse existing OpportunityDetectorV1/causal structure path for Trend and existing build_range_family_evidence for Range; preserve strategy_family_journal_v1 and paper cohort ledgers.\n- [x] Add causal Breakout/Retest and Volatility Expansion research-only OHLCV feature evaluators; no new market-data adapter.
- [x] Freeze their v1 feature definitions and threshold hypotheses in STRATEGY_FAMILY_RESEARCH_PROTOCOL_V1_2026-11-10.md; historical walk-forward/OOS validation remains open.
- [x] Persist four-family research assessment inside existing decision journal gate_evidence; validate/project it in trade_journal_view_v1; expose per-family statuses in existing dashboard journal.\n- [x] Extend existing read-only Learning Loop to produce HYPOTHESIS_ONLY feature-failure attribution from validated journal projections.
- [x] Require exact 15m source-window SHA-256, per-family evidence SHA-256, matching observation timestamps and false authority flags; no backfill or retroactive family assignment.

## Phase 3 — research and simulation
- [ ] Run chronological family-specific research over persisted Gate.io closed 15m rows; 1m remains precision-only and must not originate setup.
- [ ] Use chronological train/validation/holdout, walk-forward, conservative stop-first intrabar resolution and immutable cost assumptions.
- [ ] Verify actual execution product, fee tier, spread/slippage and funding/borrow before any net-performance claim.
- [ ] Publish family-isolated cohort reports with uncertainty intervals; no sample quota or parameter tuning on holdout.

## Phase 4 — app integration and delivery
- [x] Extend existing dashboard/API rather than rebuild; display family state, regime, research eligibility, rejection reasons, feature coverage, estimated net-R/cost context and evidence hash.
- [ ] Publish follow-up integration as a draft PR, obtain exact-head CI and independent review, and preserve the HOLD gate.
- [ ] Keep all new families research-only unless individually promoted through explicit approval.
- [ ] Immutable release, encrypted Dropbox backup/restore verification, and explicit user authorization before any production promotion.

## Current stop conditions
No live execution, no Risk Gate weakening, no 1m independent setup, no policy mutation, no forced daily trade quota, no claim of >90% performance without verified evidence.