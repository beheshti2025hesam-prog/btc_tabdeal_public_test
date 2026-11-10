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
- [x] Add versioned four-family research dispatch contract without changing the existing router.
- [x] Add a closed-15m, evidence-bound research dispatcher prototype that only marks research eligibility; actual persisted feature wiring remains open.
- [x] Keep candidate generation, confirmation, Risk, activation and execution false.
- [x] Add deterministic tests for regime/context routing, stale/invalid evidence, unknown regimes, multiple eligible families, 1m non-authority and fail-closed behavior.
- [ ] Replay existing trend baseline to prove no behavior change.

## Phase 1 validation
- [x] Isolated full repository suite: 1,308 passed + 82 subtests.
- [x] Focused family suite: 75 passed.
- [x] Exact-head GitHub CI: 32/32 successful on commit 31323d92dee4e25e96cfec313b4f00721c8a7231.
- [ ] Independent review of PR #491.

## Phase 2 — family evaluators and journal
- [ ] Wire the existing StrategyEvidenceProviderV1 (Trend) and build_range_family_evidence (Range) into research dispatch; preserve existing strategy_family_journal_v1 and paper cohort ledgers. Do not add parallel ledgers.
- [ ] Add Breakout/Retest and Volatility Expansion as research-only evaluators only after historical data contracts and preregistered hypotheses exist; reuse market_structure_v1, structure_policy_v1, order_block_v1 and core volatility features.
- [ ] Attribute every proposal/rejection to family/version/gate; preserve rejected opportunities separately from resolved trades.
- [ ] Verify no retroactive family attribution and source-hash consistency.

## Phase 3 — research and simulation
- [ ] Use Gate.io persisted native closed 15m and forward 1m data; document REST history limits and collection gaps.
- [ ] Use chronological train/validation/holdout, walk-forward, conservative stop-first intrabar resolution and immutable cost assumptions.
- [ ] Verify actual execution product, fee tier, spread/slippage and funding/borrow before any net-performance claim.
- [ ] Publish family-isolated cohort reports with uncertainty intervals; no sample quota or parameter tuning on holdout.

## Phase 4 — app integration and delivery
- [ ] Extend existing dashboard/API rather than rebuild; display family lifecycle, regime, research eligibility, rejection reasons, cohort sufficiency and metrics.
- [ ] Exact-head CI, independent review and evidence gates.
- [ ] Keep all new families research-only unless individually promoted through explicit approval.
- [ ] Immutable release, encrypted Dropbox backup/restore verification, and explicit user authorization before any production promotion.

## Current stop conditions
No live execution, no Risk Gate weakening, no 1m independent setup, no policy mutation, no forced daily trade quota, no claim of >90% performance without verified evidence.