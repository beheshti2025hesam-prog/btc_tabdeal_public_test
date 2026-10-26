# HES Trade Agent — Progress Dashboard & 24h Delta
**Checkpoint date:** 2026-10-26 (UTC)  
**Target delivery:** 2026-11-19  
**State:** HOLD / NO_TRADE_ONLY; execution OFF.  
**Authority model:** Memory = project map; GitHub = technical truth; Chat = conversation log; this file + Master Checkpoint + checklist = resume point.

## 1. Progress scoring rule (fixed for future comparisons)
This is an evidence-weighted **delivery maturity index**, not a claim that a percentage of code is finished, not a trading-performance probability, and not release readiness. Each workstream has a fixed weight; its maturity score is 0–100 based only on documented evidence. The overall score is the sum of (weight × maturity)/100. Keep this same rubric for later checkpoints. Add points only when new, valid evidence closes work. If evidence is invalidated, preserve the historical score and record the regression as a separate red status; do not silently rewrite past checkpoints. The 2026-10-25 baseline below is reconstructed from the prior written checkpoint because a formally archived percentage was not found.

## 2. Weighted progress by workstream

| Workstream | Weight | 2026-10-25 baseline maturity | 2026-10-26 maturity | Weighted contribution now | Evidence / remaining limitation |
|---|---:|---:|---:|---:|---|
| Canonical architecture and single-source data contract | 10% | 100% | 100% | 10.00 pp | Locked: one global candle source to chart/analysis; exchange adapter is for execution/order status only. No reopening generic sequence semantics without new evidence. |
| Feed integrity and multi-timeframe reader | 10% | 80% | 90% | 9.00 pp | 15m/1h/4h canonical reader validated; unique/increasing timestamps. Score remains 90 because this is one venue's public spot feed, not consolidated market data. |
| Continuous 24h soak + independent audit | 10% | 0% | 100% | 10.00 pp | PASS: 86,400 seconds, 1,439 samples, max gap 60.742s, no errors; independent audit and SHA-256 verified. |
| Restart/reconnect resilience | 10% | 10% | 60% | 6.00 pp | Controlled service restart PASS; mocked reconnect harness PASS. Live network disconnect/reconnect fault injection remains NOT RUN; WebSocket live smoke is SKIPPED. |
| Dashboard + Signal Agent same-batch integration | 15% | 35% | 90% | 13.50 pp | Draft PR #388 exact-head full suite and browser/single-path checks PASS; chart and Signal Agent batch hashes match. Not production runtime proof. |
| Production frontend runtime/deployment/rollback | 15% | 0% | 0% | 0.00 pp | BLOCKED: no dashboard service/deployment verified on the sole VPS; no deployment authorized. |
| Strategy structure, confirmation, quality evidence | 10% | 10% | 10% | 1.00 pp | Providers and strategy approval still unapproved; fail-closed behavior retained. |
| Independent risk approval and gate-bypass resistance | 10% | 20% | 20% | 2.00 pp | NO_TRADE / execution disabled validated; independent risk approval and full release-grade approval still missing. |
| Venue symbol/instrument mapping and execution boundary | 5% | 0% | 0% | 0.00 pp | BLOCKED: no independently approved executable symbol/instrument mapping; no order placement. |
| Operations, PR lineage, security and release review | 5% | 20% | 25% | 1.25 pp | Checkpoint/evidence provenance improved; PRs remain Draft/HOLD with no submitted reviews. OS/security release audit and final rollback plan remain open. |
| **Overall evidence-weighted index** | **100%** |  |  | **52.75%** | Rounded report: **52.8%**. |

### Day-over-day comparison (same rubric)
- **2026-10-25 reconstructed baseline:** 28.25% (rounded 28.3%).
- **2026-10-26 current:** 52.75% (rounded 52.8%).
- **Net evidence-backed increase:** **+24.50 percentage points**.
- The increase is mainly attributable to the completed 24-hour soak/audit, controlled restart plus mocked reconnect evidence, and exact-head dashboard/Signal Agent CI. This is not a promise of 52.8% deployability; mandatory production, strategy, risk, mapping and review gates remain open.
- The previous day did not have a formally archived numeric percentage located during this checkpoint. The baseline is therefore explicitly reconstructed from documented gate maturity, not represented as a previously published score.

## 3. Simple visual

```text
2026-10-25  28.3%  ██████████████░░░░░░░░░░░░░░░░░░░░░░░░░░
2026-10-26  52.8%  ██████████████████████████░░░░░░░░░░░░░░
```

The bars are a visual encoding of the same weighted index above; they are not an independent metric.

## 4. Runs and evidence reviewed on 2026-10-26

Candidate: [Draft PR #388](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388)  
Exact head checked: `b5674b5b785327c17b143df724e8a43776d88062`.

| Run | Check | Result |
|---|---|---|
| [40318556296](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40318556296) | Full repository regression | PASS — 599 passed, 5 subtests passed |
| [40318556307](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40318556307) | Dashboard single-path | PASS |
| [40318556297](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40318556297) | Browser render/pixel | PASS |
| [40318556459](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40318556459) | Native OHLCV WebSocket live smoke | SKIPPED — not a pass; do not rerun as a live test without an authorized bounded test plan |

Browser evidence: 239 closed candles; displayed close/volume match source; chart and Signal Agent share batch SHA-256 `d4902b9d6d0150801247710705399322116f917fef97686e3e0ab01307bd34bc`; browser made no direct exchange REST request; execution remained disabled.

### Feed soak and recovery evidence
- Soak log SHA-256: `df499e17f6366e69ab14ab17adc2ed7e2ac9e205e4d1b1925bbd6284de975c44`.
- Independent audit report SHA-256: `ecc9dff5780edfb8d25e32bab698a27f362dc16b7dedbc549430f4990bfdc8bd`.
- Controlled restart evidence SHA-256: `426620bc806b2ead26843e0e361ca1b658468b3e2d69d3cf67cd16da65968d0f`.
- Mock reconnect evidence SHA-256: `83e542916153cceceb349fa6a9895f40c25841a1c0accb08d0f8afb4169bc9f2`.
- Post-restart one-shot analysis: `NO_TRADE`; `execution_enabled=false`; `orders_placed=false`.

## 5. Runtime / working tree truth
- Sole connected VPS target: SentinelX reports one active host; do not infer a second VPS from its machine label.
- Repository: `/opt/hes-trade-agent`; branch `feat/gateio-global-market-data-v1`; HEAD `b2466bc118217dcc6446498effe38181589ed2db`.
- Dirty checkout remains intentionally preserved: 11 tracked modifications and 50 untracked paths (61 status entries). **Do not reset, clean, checkout over, or bulk overwrite.**
- Gate.io services for 15m/1h/4h were active after the controlled restart. The completed soak service is inactive as expected.
- Legacy `hes-trade-agent-collector.service` remains disabled/failed after its final checkpoint refused a stale remote base. It was not restarted because it is not the canonical chart/analysis source; decide separately whether to repair persistence or retire it.
- Production dashboard service/runtime remains unverified and was not deployed.

## 6. Checklist — resume from the first open item
- [x] Preserve the one-global-source architecture and no-generic-sequence-reconciliation rule.
- [x] Complete and independently audit the 24-hour read-only Gate.io soak.
- [x] Perform controlled restart/recovery and verify canonical 15m/1h/4h feed continuity.
- [x] Review exact-head PR #388 CI and same-batch browser evidence.
- [x] Confirm current analysis remains NO_TRADE with execution OFF.
- [x] Save current evidence hashes and update this checkpoint.
- [ ] Verify actual frontend runtime, service route, security settings, and rollback path on the sole VPS; no deploy until approved.
- [ ] Complete live WebSocket fault-injection under a bounded authorized plan; current smoke is SKIPPED.
- [ ] Independently approve strategy structure/confirmation/quality providers.
- [ ] Independently approve risk policy and prove no signal/risk bypass.
- [ ] Prove venue symbol/instrument mapping and order-status/fill contract; keep execution OFF.
- [ ] Review PR ancestry/overlap; obtain independent review; run final exact-SHA checks.
- [ ] Complete operational/security checks and final go/no-go.

## 7. Next continuation point
Start with **frontend runtime identity and rollback evidence on the sole VPS**, read-only first. Preserve dirty checkout. Do not deploy, merge, activate a service, or trade. In parallel, review PR #388 ancestry and release gates; do not independently merge overlapping #383/#387 candidates. Keep delivery target **2026-11-19** and state **HOLD / NO_TRADE_ONLY**.
