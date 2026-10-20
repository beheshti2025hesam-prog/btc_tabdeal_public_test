# HES Trade Agent — Master Checkpoint
**Checkpoint date:** 2026-10-20 (project timezone Asia/Tehran, evening)  
**Checkpoint commit reviewed:** `22f704489c43f4b9818588379ef1cdd550505cd2`  
**Repository:** https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test  
**Active PR:** #340 — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/340  
**Status:** OPEN, NOT MERGED. This checkpoint records evidence and estimates; it does not authorize production deployment or trading.

## Three sources of truth
- **Memory = project map and continuity context.** Preserve the non-negotiable architecture and next actions between conversations.
- **GitHub = technical truth.** Code, commits, CI, ADRs and PR review evidence outrank conversational recollection.
- **Chat = conversation log.** Use it to understand decisions and intent, but verify implementation in GitHub.
- This document is the master checkpoint to resume from. Update it only when new evidence is verified.

## Non-negotiable project architecture
1. Market chart/candles and analysis data must come from a qualified independent/global provider (TradingView datafeed with a real licensed data source or equivalent). Do NOT use the execution exchange's chart/candles as the analysis source.
2. The execution venue is only for orders, fills, account/venue constraints and reconciliation.
3. One qualified data source should feed both chart display and strategy analysis; retain provider, instrument, interval, timestamps and lineage.
4. No invented aggregation, inferred volume semantics, silent rescaling, or claims without raw evidence.
5. Fail closed: until provider, strategy, risk and execution checks are proven, remain `HOLD / NO_TRADE_ONLY`, `live_execution_enabled=false`, no live orders.
6. Do not create a parallel application if the existing repository has a real path; extend the actual repository.
7. Production VPS must not be modified while its working tree has uncommitted user changes and write authorization is absent.

## Verified GitHub state at this checkpoint
- PR #340 is open and unmerged.
- A read-only dashboard slice exists at `web/dashboard.py`, bound to loopback by default. It has no order-submit route.
- Yahoo Finance is explicitly labelled an **unverified USD reference only**, not a certified global aggregate and not an approved strategy input.
- Source volume is preserved as received. A live smoke sample returned volume `0`; volume-dependent features remain disabled.
- The source-qualification ADR documents TradingView's datafeed limitation and CoinDesk Data API licensing/history/endpoint-scope constraints: `docs/decisions/ADR-2026-10-20-market-data-source-qualification.md`.
- The dashboard ADR is `docs/decisions/ADR-2026-10-20-integrated-readonly-dashboard.md`.
- Focused dashboard suite reported 14 passing tests at code head `68f1cdeeff3fdcba3edfdd58f28c95731b6c47f1`: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39482140731
- Latest reviewed head `22f704489c43f4b9818588379ef1cdd550505cd2`: 27 workflow runs associated with that commit were returned by GitHub Actions; **27/27 completed successfully**. Run list includes dashboard tests, canary, identity integrity, strategy/feature-engine tests, risk boundary, data foundation, backtest, forward integration and related audits. Eight representative runs/jobs were inspected and showed success with no failed steps. Aggregate run query evidence was retrieved live during this checkpoint; no failed run was found in that commit's returned set.
- Latest focused dashboard workflow: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39482523968
- No live order was sent. No production deployment or VPS write was performed.
- The current PR body cites the 14-test evidence from the earlier tested code head and the focused workflow at the later ADR head. Do not confuse focused-suite success with end-to-end readiness or production certification.

## Overall progress estimate — provisional, evidence-based workstream rubric
There is no verified canonical project-wide task inventory with denominator/acceptance weights in the reviewed README/ADRs. Therefore the percentages below are **engineering estimates**, not measured completion metrics or a claim that the project is nearly ready. Re-baseline when the full master roadmap and acceptance criteria are reconciled.

| Workstream | Estimate | Evidence / remaining critical work |
|---|---:|---|
| Project principles / architecture decisions | 80% | Core separation and safety ADRs recorded; consolidate full master roadmap and all legacy decisions. |
| Data foundation / collectors | 65% | Existing collector and related CI are present; validate source quality and required market coverage end-to-end. |
| Strategy and feature-engine components | 60% | Multiple feature and strategy contract tests pass; prove a qualified feed is actually connected to the approved analysis path. |
| Market-data provider qualification | 25% | Yahoo is display-only; CoinDesk is only a candidate. License/account access, aggregation, volume semantics and raw comparison remain open. |
| Frontend / chart integration | 65% | Existing repository dashboard slice and route/parser tests exist; real provider not yet approved and strategy output not yet integrated. |
| Risk engine integration / end-to-end signal path | 40% | Risk boundary tests exist; actual source → analysis → risk evidence path still needs integration proof. |
| Exchange execution adapter / symbol and order mapping | 20% | Architecture constraint is recorded; actual adapter acceptance, order idempotency, venue constraints and fill reconciliation not proven here. |
| Automated testing / CI | 70% | 27/27 commit-associated runs succeeded and focused tests pass; tests do not substitute for provider qualification, end-to-end tests or live safety certification. |
| Deployment / operations / monitoring | 15% | No production deployment authorized; safe remote changes blocked by uncommitted production working-tree changes and absent write permission. |

**Indicative overall completion: ~45% (low-to-medium confidence).** This is a rough equal-weight workstream average, rounded, not a precise task-weighted total. The biggest project-completion blockers are provider qualification, integration of the approved feed into analysis/risk, and execution/reconciliation verification. Green CI improves confidence in tested code but does not itself add large completion percentage to unimplemented integration work.

## Work completed in the 24-hour project window (2026-10-19 to 2026-10-20; based on visible project/commit evidence)
1. Added/iterated the read-only dashboard integration in the actual HES repository rather than creating a parallel app.
2. Corrected the interval-based freshness logic and added a regression test.
3. Added a zero-volume preservation regression test; source volume is preserved, not inferred or scaled.
4. Changed unsupported Yahoo wording to provisional/unverified reference wording and disabled volume-derived strategy assumptions.
5. Added/updated source-qualification ADR to state TradingView is a charting library/datafeed interface rather than a standalone data provider, and to record CoinDesk plan licensing/history limitations and the distinction between exchange-specific OHLCV and index/reference endpoints.
6. Updated PR #340 evidence and safety language.
7. Checked the 27 workflow runs associated with commit `22f704489c43f4b9818588379ef1cdd550505cd2`; all returned runs completed successfully, with representative jobs inspected for failed steps.

### Estimated impact of the last 24 hours
- **Testing/CI confidence:** materially improved; latest reviewed commit has 27/27 successful associated workflows and focused dashboard tests passed.
- **Frontend/chart plumbing:** moved forward; read-only integrated route exists and is tested.
- **Data-provider approval:** improved clarity, but completion percentage changes only slightly; candidate research is not a connected/qualified feed.
- **End-to-end trading readiness:** no material increase claimed. The actual qualified-feed → analysis → risk → execution path remains unproven and trading stays disabled.
- Do not claim a numerical 24-hour delta from a prior baseline: no independently verified prior overall percentage/denominator was found. The current ~45% is a fresh rough baseline, not a precise before/after measurement.

## Next actions in strict order
1. Confirm whether project owner can provide/authorize an appropriate provider account/API credential and intended use/licensing. Do not ask for secrets in chat; use approved repository secret management if/when authorized.
2. Verify the documented CoinDesk aggregate/index endpoint and actual instrument definitions; capture representative raw BTC/ETH/SOL responses across required intervals. If access/license/semantics fail acceptance, evaluate another documented provider rather than treating Yahoo as approved.
3. Compare identical UTC windows, intervals and instrument definitions against independent references; verify candle closure, OHLC invariants, gaps, stale data, failure behavior, volume units/semantics, rate limits and licensing.
4. Connect the same approved source to the chart and analysis input; prove data lineage and fail-closed behavior.
5. Prove analysis output → risk engine → execution adapter; test symbol mapping, precision/minimums, duplicate-order idempotency, timeouts, partial fills and order/fill reconciliation using mocks/sandbox first.
6. Review all relevant CI for the latest head again after changes. Resolve any failing/stale check and update PR evidence; do not merge based solely on green tests if acceptance evidence is missing.
7. Revisit deployment only after repository/production state is reconciled and explicit write authorization exists.

## Resume instruction
Resume from this file and PR #340. First re-fetch live PR head, branch status, latest Actions runs and current files; do not assume this checkpoint is newer than GitHub. Preserve the architecture above. No exchange candles for analysis, no invented data, no production write, no live trade until all gates pass.
