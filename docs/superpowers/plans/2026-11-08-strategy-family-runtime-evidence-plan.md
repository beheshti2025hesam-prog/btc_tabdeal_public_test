# Plan: Strategy-family runtime evidence and research dispatch

**Spec:** `docs/superpowers/specs/2026-11-08-strategy-family-runtime-evidence-design.md`
**Base:** `f5d505567522555ee1be9c260e83085347515721`
**Worktree:** `/opt/hes-trade-agent/.worktrees/strategy-family-confirmation-20261107`
**Branch:** `feat/strategy-family-confirmation-v1`

## Global constraints

Use only persisted Gate.io Spot BTC_USDT frames from the existing reader. Reuse existing native candle, feature, strategy evidence, family confirmation/context, journal and Risk Gate components. No network fetch, no service mutation, no release change, no real execution, no Risk Gate or 3R weakening. Trend path must remain equivalent. Range remains research-only. The family evaluation contract remains independent by family and requires >90% over >=100 resolved trades plus independent OOS and verified costs.

## Task 1 — Persisted Gate.io rows to native batches

- Add a narrow converter for validated `global_market_data_reader_v1` rows to `NativeOHLCVBatch`.
- Preserve exact Gate.io scope, candle times, quote/base volume, per-timeframe source hashes and unavailable flow fields as `None`.
- Reject source/symbol/timeframe mismatch, open bars, gaps, stale/future timestamps, invalid OHLCV and malformed timestamps.
- Tests: valid canonical conversion; wrong source/symbol; wrong timeframe; fabricated flow rejected; malformed/duplicate/gap rows rejected; exact persisted-window hash changes when source row changes.
- Expected: focused adapter tests pass; no existing reader or Gate.io adapter tests regress.

## Task 2 — Causal Range family evidence builder

- Reuse `StrategyEvidenceProviderV1.adx14`, `mfi14_series`, existing `EMACalculator`, and the existing sweep/reclaim research policy.
- Build 15m/1h/4h ADX, 1h/4h EMA50 slope normalized by ATR14, prior-only range boundaries, disjoint persistence window, MFI reversal and simulation-cost evidence.
- Emit a family-bound candidate with a real SHA-256 over source evidence and feature values; create the exact eight Range confirmation checks with source/time-bound evidence references.
- Tests: deterministic long/short sweep/reclaim; no-lookahead boundary; persistence window; source gaps/stale/missing data; non-finite features; missing Gate.io flow remains unknown; costs are labelled assumptions.
- Expected: only a complete, causal, canonical Gate.io Range candidate can produce all eight PASS checks.

## Task 3 — Family dispatch in the existing forward pipeline

- Add an additive family confirmation result to `evaluate_gate_evidence`.
- Trend delegates to the existing three-check `ConfirmationPolicyV1`; verify old Trend confirmation/risk/final-decision output is unchanged.
- Range uses the new candidate and independent eight-check contract; shared `RiskGateV1` must reject `RESEARCH_CONFIRMED_*`; final decision remains NO_TRADE.
- Build the existing digest-bound family context for either family without granting candidate-generation, risk, or execution authority.
- Tests: Trend replay equivalence; Range dispatch; Risk Gate rejection; tampered source/digest/time; no 1m setup; execution flags false.
- Expected: pipeline exposes family evidence and independent confirmation while preserving existing global safety behavior.

## Task 4 — Existing journal attribution and documentation

- Ensure the existing decision journal stores the family candidate/confirmation/evidence as immutable fields within its current decision event. Do not add a parallel journal or mutate outcomes.
- Verify `ForwardJournalV1` rejects duplicate event IDs and future outcome leakage; verify `trade_journal_view_v1` projects family identity correctly.
- Document the remaining raw family outcome cohort work separately; do not manufacture acceptance reports from synthetic data.
- Expected: one existing journal record per closed 15m decision carries family provenance; Trend and Range cohorts remain separable.

## Task 5 — Verification and review

- Run focused tests with warnings as errors, then the full repository suite.
- Run `git diff --check`; inspect exact diff, active release identity and safety flags.
- Record any environment-only baseline failures separately; do not mask them.
- No deployment, merge, remote push, or live-trading change in this plan.

## Review focus

- No data source duplication or stale/future candle acceptance.
- No lookahead in range boundary/persistence calculations.
- No mislabelling MFI base-volume evidence as taker-buy flow.
- No Range-to-RiskGate authorization path.
- No Trend output regression or family cohort mixing.
- No fabricated >90% metrics or activation state.

## Execution status — 2026-11-08

- [x] Task 1 — persisted Gate.io rows to native batches.
- [x] Task 2 — causal Range family evidence builder.
- [x] Task 3 — independent family dispatch with shared Risk Gate veto.
- [x] Task 4 — family attribution in the existing append-only decision journal and journal view. Raw family outcome cohort/report producer is explicitly deferred to the next P0, not claimed complete.
- [x] Task 5 — focused and full-suite verification; compile and diff checks.
- [ ] Local commit / remote publication — blocked: Git object database returned `insufficient permission` during `git add`. No permission changes or workaround attempted. The remote PR branch remains unchanged; ask for explicit approval before publishing.

Verification: focused suite **151 passed**; full suite **1,240 passed + 82 subtests passed in 14.74s** with warnings treated as errors; `py_compile` and `git diff --check` passed. Active release and paper services were unchanged; no deployment or live execution.