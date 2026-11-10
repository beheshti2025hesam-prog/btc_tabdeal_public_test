# Strategy Family Intelligence — Implementation Plan

**Base:** PR #480 head 1f81f90897441c3501c802416ed300c4725de2d2  
**Isolation:** detached worktree /tmp/hes-strategy-intelligence-20261110; primary checkout untouched.

## Phase 0 — preserve and inventory
- [x] Capture approved architecture in Notion Master Checkpoint.
- [x] Confirm current router/context/confirmation/evaluation/paper cohort modules exist.
- [x] Confirm the primary checkout is dirty and must not be reset/cleaned.
- [x] Create isolated worktree from PR #480 head.
- [ ] Map existing family IDs, schemas and downstream hard-coded profile registries.
- [ ] Reconcile PR #480's review/CI before treating it as a stable merge base.

## Phase 1 — contracts and research dispatch
- [ ] Add versioned four-family research catalog without changing the existing router.
- [ ] Add closed-15m, evidence-bound orchestrator that only marks research eligibility.
- [ ] Keep candidate generation, confirmation, Risk, activation and execution false.
- [ ] Add deterministic tests for regime/context routing, stale/invalid evidence, unknown regimes, multiple eligible families, 1m non-authority and fail-closed behavior.
- [ ] Replay existing trend baseline to prove no behavior change.

## Phase 2 — family evaluators and journal
- [ ] Map and reuse current Trend/Range evaluators and journal; do not create parallel ledgers if existing schemas suffice.
- [ ] Add Breakout/Retest and Volatility Expansion as research-only evaluators only after historical data contracts and preregistered hypotheses exist.
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