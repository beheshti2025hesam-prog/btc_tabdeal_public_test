# HES Trade Agent — Release Readiness Contract
**Checkpoint date:** 2026-10-29  
**Target delivery:** 2026-11-19  
**Release state:** HOLD / NO_TRADE_ONLY  
**Scope:** documentation and evidence-led release planning only. This document does not authorize merge, deployment, collector activation, credentials use, or trading.

## Release decision
The project is not release-ready on current evidence. The critical blocker is not a missing new frontend implementation: the authorized production frontend repository/path and exact runtime acceptance target have not been verified. Do not build a parallel frontend or replace existing application components to work around this gap.

## Evidence-backed repository/runtime map
- Master checkpoint #350 and roadmap issue #334 were re-read on 2026-10-29. These are the strongest detailed historical checkpoints found in the connected repository and supersede any casual assumptions in chat.
- Active source decision in issue #334: Gate.io public Spot `BTC_USDT`, intervals `15m`/`1h`/`4h`, via PR #365. Do not revive Binance PR #345 as the default source without a new evidence-based decision. The historical report records REST HTTP 200 and source-to-canonical parity, but explicitly says this is not rendered-chart parity or production freshness approval. It also records an incomplete soak and no valid paper-performance sample.
- Connected GitHub project repository visible to the connected account: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- Its default-branch `README.md` identifies it as the first Tabdeal BTC/USDT futures public market-data collector/data-foundation component. It explicitly does not place orders or trade. This repository is verified as project/data-foundation, but not proven to be the complete production frontend/application repository.
- Existing single VPS checkout was reported by issue #348 as `/opt/hes-trade-agent`, branch `main`, HEAD `4956cf519c44`. That report also records a dirty tree (10 unstaged changes, 30 untracked files, 418 deletions in summary). Treat that checkout as protected evidence: do not reset, clean, overwrite, or deploy from it.
- Issue #348 states that the connected GitHub account exposes only the data-foundation repository and that the real frontend repo/path and approved outbound market-data policy must be made visible/confirmed. The user has confirmed there is only one VPS; a misleading device label does not indicate a second server.
- Issue #334 records Gate.io public Spot `BTC_USDT` 15m/1h/4h via PR #365 as the active source decision in that checkpoint, and says not to revive Binance PR #345 as default. PR #365 was described as Draft/unmerged at head `01ca14807ab8875336bbbade5c3c9c9be5e447f3`, base `4956cf519c445edd004fdd4e763bdb3347a7ada9`, with 26/26 workflows successful at that reported exact head and read-only REST checks returning HTTP 200. These are historical reported results and must be rechecked against current exact SHAs before release.
- PR #297 describes native OHLCV adapters and validation. Its reported live evidence includes successful Spot endpoint parity but explicitly leaves USDⓈ-M Futures direct raw-HTTP capture blocked by HTTP 451, and notes no documented Tabdeal candle endpoint. Do not reinterpret Spot parity as Futures/Tabdeal proof.
- PR #346 is a candidate dashboard/native-data path, not production approval. Historical branch CI results do not substitute for target-runtime acceptance; its live WebSocket smoke was reported as SKIPPED, not passed.
- PR #386 is documentation-only release-readiness/checkpoint work and explicitly retains unresolved evidence gates.
- Current repository-map checkpoint: [MASTER_CHECKPOINT_2026-10-29_REPOSITORY_MAP.md](checkpoints/MASTER_CHECKPOINT_2026-10-29_REPOSITORY_MAP.md).

## Anti-reinvention / architecture rules
1. Inventory existing files, imports, callers, tests, migrations, and PR diffs before proposing code. Reuse proven modules; avoid parallel applications, dashboards, journal schemas, indicator calculations, or candle pipelines.
2. Canonical analysis feed and execution venue are separate concerns. Keep one approved market-data source → analysis → risk/decision path; exchange adapter handles execution/order status only. Add trade-sequence reconciliation only if a documented execution-critical need and authoritative semantics require it.
3. Do not silently promote a candidate PR, a historical CI result, a connector snapshot, or a screenshot into fresh runtime evidence.
4. Never expose secrets, use private API calls, place orders, activate a collector, or deploy as part of documentation/readiness work.
5. The only VPS is `/opt/hes-trade-agent` as reported in issue #348; do not assume or create a second VPS.
6. Preserve the dirty runtime workspace. No destructive git commands, cleanup, overwrites, or unapproved service changes.
7. Keep Free-First / Zero-Cost defaults. Paid services require a separate documented justification and approval.

## Newly clarified historical evidence (reviewed 2026-10-29)
- Issue #350 states PR #297, #344, #345, #346, #347, and #349 were Draft/unmerged at that checkpoint; #340 and #346 have competing dashboard paths that must be reconciled before merge.
- The recorded successful PR CI/browser-render checks are GitHub-runner evidence only. PR #346's live WebSocket smoke was SKIPPED, not passed.
- Issue #334 records Gate.io source REST checks as successful but a soak shorter than 24 hours and paper performance as `NO VALID SAMPLE / NOT RUNNING`. Journal records had no run-bound source SHA or resolved outcomes in that historical snapshot.
- Issue #334 also records a policy-runner safety gap: potential candidates were not routed through all fail-closed signal/confirmation/risk gates. Until proven fixed on the current exact SHA, treat any candidate from that path as `NO_TRADE`.

## Gate checklist
- [x] Identify the currently accessible HES project/data-foundation repository and record its limitation.
- [x] Record the reported single-VPS path/branch/HEAD and dirty-tree warning from issue #348.
- [x] Record the delivery target and candidate PR lineage without claiming approval.
- [ ] Owner restores authorized visibility to the actual production app/frontend repository or confirms the exact existing project path in an accessible workspace.
- [ ] Owner confirms approved outbound access policy for the selected public market-data source on the single VPS.
- [ ] Read-only inspect current VPS identity, git status, branch and exact HEAD; do not mutate the dirty checkout.
- [ ] Identify actual production app entrypoint from repository files, import graph, service configuration, and runtime evidence.
- [ ] Verify existing dashboard, OHLCV contract, journal, API, and learning-loop implementations; document exact paths and tests before changing anything.
- [ ] Recheck PRs #297, #346, #354, #365, #375, #386 for current state, exact head/base SHA, changed files, overlap, CI and review state.
- [ ] Pin exact-SHA CI, artifact provenance, raw-source evidence and runtime test evidence for the intended release candidate.
- [ ] Test stale/closed-candle handling, reconnect/recovery, duplicate/order-intent prevention, risk veto/NO TRADE, journal replay/integrity, and UI/API projection on the approved target.
- [ ] Document reproducible install/configuration, environment variables and secrets handling, backup/restore, health checks, logs, rollback and operator runbook by extending existing docs.
- [ ] Independent review of the release bundle; no readiness claim until all required gates pass.

## Delivery management
- Fixed target date: **2026-11-19**.
- Immediate critical path: restore access/visibility to the existing frontend repository/path and confirm outbound market-data policy; then exact-SHA review and read-only target-runtime acceptance.
- Do not spend schedule rebuilding components that already exist. If a required gate remains blocked, report the blocker and impact transparently rather than declaring completion.
- Current release decision remains **HOLD / NO_TRADE_ONLY** until all applicable gates pass.

## Change log
- 2026-10-29: Added evidence-backed release contract on the separate documentation branch. Documentation-only; no application code, VPS, runtime, services, or trading behavior changed.
