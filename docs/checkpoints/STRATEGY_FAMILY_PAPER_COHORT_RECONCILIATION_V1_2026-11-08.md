# HES Trade Agent — Family-Isolated Paper Outcome Cohorts & Reconciliation

**Date:** 2026-11-08  
**Branch/worktree:** feat/strategy-family-confirmation-v1 /opt/hes-trade-agent/.worktrees/strategy-family-confirmation-20261107  
**Base:** PR #480 head cfd2783f9d3a5ee0e3c02e7d2436e5f30ea219e6  
**Active release:** unchanged f5d505567522555ee1be9c260e83085347515721  
**Disposition:** IMPLEMENTED IN ISOLATED WORKTREE / TESTED / NOT PUBLISHED OR DEPLOYED / PAPER-ONLY.

## Objective

Complete the next P0 after family-specific runtime evidence dispatch: resolve and reconcile paper outcomes independently for each strategy family, without changing the shared Risk Gate, activating a strategy, or enabling real execution.

## Reused components — no parallel infrastructure

- Existing global_market_data_reader_v1 persisted Gate.io Spot BTC_USDT closed-candle rows (15m setup authority); no new REST/WebSocket path.
- Existing trade_journal_v2.jsonl decision events and ForwardJournalV1 append-only/idempotent writer.
- Existing family router, family evidence/context/confirmation contracts, and strategy_family_evaluation_v1 acceptance coordinator.
- Existing 15m paper candle-path resolution semantics. Extracted once into forward/paper_outcome_resolver_v1.py and used by both the existing Strategy V2 paper evaluator and the new family cohort reader. This preserves stop/target order, conservative same-candle stop precedence, and the 24h timeout behavior instead of maintaining two competing resolvers.

## Delivered

1. forward/paper_outcome_resolver_v1.py — shared deterministic 15m paper outcome resolver used by the legacy evaluator and family cohort.
2. forward/strategy_family_paper_cohort_v1.py — family-bound candidate extraction, append-only candidate/outcome ledgers, strict outcome-to-candidate matching, cost-aware net-R scoring, per-family reports, and invocation of the existing family acceptance coordinator.
3. scripts/run_strategy_policy_v2_forward_eval.py — the existing paper evaluator now records candidate_time, invokes family reconciliation from its existing closed 15m frame, and includes the result in its report. No second service or journal was introduced.
4. New deterministic tests:
   - tests/strategy/test_paper_outcome_resolver_v1.py
   - tests/strategy/test_strategy_family_paper_cohort_v1.py

## Reconciliation rules

- Only explicit, version-matched family route + candidate + confirmation + verified context can enter a family cohort.
- Candidate and outcome are joined only by stable candidate_event_id; timestamp fallback is disabled.
- Family ID, family version, direction, source, symbol, timeframe, provenance, and paper-only safety flags are checked. Cross-family, duplicate, unmatched, or unsafe records are not pooled.
- Trend candidates count toward the acceptance cohort only when the family confirmation is CONFIRMED_*, the shared Risk Gate is RISK_APPROVED, and the final decision is directional.
- Range RESEARCH_CONFIRMED_* outcomes are recorded as research_shadow_only; they remain excluded from acceptance because the unchanged shared Risk Gate rejects research confirmation. No Range exception or bypass is introduced.
- Outcomes are resolved from later closed 15m Gate.io candles only. Same-candle stop+target is a conservative loss. Timeouts are marked separately. Entry is a closed-candle reference simulation, not an exchange fill.
- Fee/slippage currently remain ASSUMPTION_BASED; the family acceptance coordinator requires verified costs, >=100 resolved trades per family, strictly >90% win rate, positive net expectancy, PF>1, independent OOS evidence, and the global <=3 actionable signals/UTC day cap (cap, not quota).
- Reports distinguish research-shadow metrics from acceptance-eligible metrics. No synthetic OOS report or verified-cost claim is generated.

## Live-data dry-run on the sole VPS — read-only

- The active journal contains 315 records with an explicit Trend/Range family route but no family candidate/confirmation payload in the active release. They are not silently converted into trades.
- The legacy Strategy V2 paper ledgers contain 37 candidates and 37 outcomes (30 losses, 6 wins, 1 timeout); their family ID is absent and their candidates are NO_TRADE. They are deliberately excluded from both family cohorts.
- One-shot evaluation of the latest persisted Gate.io 15m batch in the isolated worktree routed the current regime to range_mean_reversion, but the Range evidence builder returned NO_CANDIDATE (TREND_STRENGTH_TOO_HIGH). Family confirmation stayed UNCONFIRMED; the shared Risk Gate remained RISK_REJECTED; final decision remained NO_TRADE.
- Read-only reconciliation returned NO_FAMILY_CANDIDATES_YET and acceptance NOT_MET. It created no runtime ledger/report files. No candidate/outcome/report ledger exists in the active data directory yet because the feature worktree has not been deployed.

## Verification

- Focused family/cohort/resolver/journal suite: 92 passed before shared-resolver extraction; latest focused resolver/cohort/evaluator suite: 27 passed.
- Full repository suite after all changes: 1,253 passed + 82 subtests passed in 12.76s, warnings treated as errors.
- py_compile/compileall: passed.
- git diff --check: passed.
- SHA-256:
  - forward/paper_outcome_resolver_v1.py: e8a3300e863919c90854cd3ae7202a7222a430a9f86121a95983ca7323eb141d
  - forward/strategy_family_paper_cohort_v1.py: aaa86874938c56ae704d60edb26d7eb627190311643f4bf333722a2616ecfdef
  - scripts/run_strategy_policy_v2_forward_eval.py: 05cfce3b08ebf1be59cd34db2b7efb043e64459d4886e72db207f96208357ac0
  - tests/strategy/test_paper_outcome_resolver_v1.py: 57f5bc96184c21537e74848a3740f98d9ae223eff722bcce38e436cd70a8c162
  - tests/strategy/test_strategy_family_paper_cohort_v1.py: 202487902adac59fe88f3f15f7c1b1a2ccfe81ab59e83760587aff2ba272f2f8

## Safety and publication status

- Active release pointer remains f5d505...; hes-strategy-paper-evaluator, hes-strategy-learning-loop, and hes-precision-entry-journal remained active with their pre-existing start times.
- No service restart, release switch, merge, push, credentials change, Risk Gate edit, 3R change, execution adapter change, or live order occurred.
- The branch worktree remains uncommitted. Git object database permissions previously blocked git add; no permission/ownership workaround was attempted. Remote PR #480 was not updated. The existing isolated worktree's other in-progress changes were preserved.

## Remaining gates

1. Obtain approval to publish the fully tested worktree changes to the existing PR branch; do not force ownership or permission changes.
2. After reviewed merge and separately approved release, let the existing evaluator append family candidates/outcomes and verify idempotent live ledger growth.
3. Accumulate >=100 resolved eligible outcomes independently for each family; do not count shadow-only Range results as approved trades.
4. Supply independently verified fee/slippage evidence and chronological independent OOS reports for each family.
5. Re-run exact-SHA full regression and independent review before any strategy activation. Live execution remains separately unauthorized.

**Invariant:** execution_enabled=false; orders_placed=false; risk_gate_modified=false; no family acceptance PASS or win-rate claim is currently established.


## 2026-11-10 integration addendum — family cohorts connected to journal and learning

**New disposition:** integrated and regression-tested in the isolated continuation worktree based on PR #480's reconciled head 55b51d4a3f2624b80ac5142802aa53bb4211c86a; not yet published or deployed.

- The existing Strategy V2 evaluator now reuses the shared paper_outcome_resolver_v1 for its original 15m paper candidate resolution and the family-isolated cohort. Existing conservative same-candle stop precedence, 24h timeout behavior, candidate IDs, family IDs, run provenance, and paper-only flags are preserved.
- The existing evaluator invokes family cohort reconciliation once at process startup and once per new closed 15m candle, not every 30-second polling cycle. It uses the existing Gate.io 15m persisted candle frame and existing decision journal; no second service, feed, or strategy engine is added.
- Family candidate extraction now verifies that the top-level candidate exactly matches the candidate bound into the hashed family context, including family activation-state/version bindings. Mismatched candidate payloads fail closed.
- The existing read-only learning loop now reads the family cohort report only after validating the outer report hash, each family report hash, source-ledger and cost-context hashes, family ID/version, independent cohort identity, report freshness (maximum 30 minutes), and all paper-only/no-execution boundaries.
- Learning emits separate Trend and Range family hypotheses and reports their acceptance blockers without mixing either family into the global Strategy V2 win-rate denominator. Missing/stale/corrupt family reports produce a pipeline-integrity hypothesis, not inferred trades or policy changes.
- Full repository regression after this integration: **1,293 passed + 82 subtests**; focused family/cohort/journal/learning suite: **74 passed**; py_compile and git diff --check passed.
- The family cohort still cannot pass acceptance: verified fee/slippage evidence, at least 100 eligible resolved trades per family, strictly >90% win rate, positive net expectancy, PF>1, and independent OOS evidence remain required. Range remains research-shadow while the shared Risk Gate rejects it.
- No active release, VPS service, live journal, runtime policy, Risk Gate, or execution configuration was changed. No live order was placed. The PR remains draft until its new exact-head CI and review complete.

**Next gate:** publish this additive continuation to the existing PR branch only after local verification, rerun exact-head CI, keep it draft/HOLD, and do not merge or deploy until independent review and the evidence gates are satisfied.