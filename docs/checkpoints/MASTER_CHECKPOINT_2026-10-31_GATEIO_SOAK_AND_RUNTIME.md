# HES Trade Agent — Master Checkpoint Addendum
**Date:** 2026-10-31 UTC  
**Purpose:** Preserve newly verified runtime evidence and the next non-duplicative delivery steps. This supplements existing Master Checkpoints; it does not replace them.  
**Canonical repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`  
**Single VPS:** SentinelX host `host_71bf104a4a9bc08c`; reported hostname `vps-second-261930` is a machine hostname, not a second VPS.  
**Target delivery:** 2026-11-19  
**Disposition:** `HOLD / NO_TRADE_ONLY`; execution remains OFF.

## Newly verified — 2026-10-31

### Gate.io 24-hour market-data soak: PASS
- The existing `hes-global-market-data-gateio-soak.service` completed normally and exited `0/SUCCESS`.
- Final append-only summary in `/opt/hes-trade-agent/data/forward/gateio_feed_soak_24h_v2.jsonl`: `passed=true`, `duration_seconds=86400`, `samples=1440`, finished `2026-10-31T08:57:06.179362Z`.
- The log contains 1,440 sample records plus one final summary record; the direct check found zero records with `"ok": false`.
- The existing Gate.io public candle services for 15m, 1h and 4h were active during final samples and remain active at inspection.
- This qualifies the recorded BTC_USDT persisted-feed soak only. It does not prove other symbols, venues, execution, strategy quality, or production release acceptance.

### Existing read-only dashboard and live data path
- Existing `hes-readonly-dashboard.service` is active on loopback `http://127.0.0.1:8765`; do not expose it publicly without a separately reviewed authentication/access-control layer.
- `GET /healthz` returned `status=ok`, mode `NO_TRADE_ONLY`, source `gateio_public_spot`, reader `global_market_data_reader_v1`, symbol mapping verified, and `execution_enabled=false`.
- Current input batch SHA-256: `80a3c0db66f4d3356887b7b169df255d98037c4e48d2dd5a6d335c30e05fb56c`. The health response reported the latest persisted candle age as about 353 seconds at the probe; continue freshness checks rather than assuming the value remains current.
- The existing `GET /api/candles` route returned HTTP 200 without query parameters. One test request using guessed query names returned HTTP 400; do not infer a route defect from an unverified query contract.
- `GET /api/signal` returned `BLOCKED / NO_TRADE`. Explicit unresolved reasons include missing validated structure provider, strategy-quality provider not wired, confirmation not valid, risk geometry missing, direction/HTF/pullback/reversal/MFI/ADX evidence missing, and execution instrument mapping not verified. This fail-closed result is expected; do not relax the gates to force a signal.

### Decision/outcome validation snapshot
- The 2026-10-31 report generation at `2026-10-31T10:16:47Z` recorded 96 NO_TRADE decisions in the rolling 24h window and 485 total decision-journal records.
- The 24–48h matured cohort had 95/96 complete gap-free 24h horizons; one was incomplete. No gate-qualified directional setup was eligible for causal-quality attribution (`evaluated_unique_decisions=0`).
- Three matured 24h TAKE_PROFIT outcomes belonged to rejected proposals; by contract these are diagnostic counterfactuals, **not** missed trades or proof that NO_TRADE was wrong. At the 1h/4h horizons, one rejected proposal later hit STOP_LOSS and three hit positive outcomes; these too remain rejected-proposal diagnostics.
- Cost model for the NO_TRADE counterfactual validator is unconfigured; do not claim net profitability, causal avoided losses, or executable missed profit.
- The separate neutral outcome tracker reported 1,258 horizon records from 459 NO_TRADE decisions, 1,168 validated closed candles, and 119 pending horizons at that snapshot. These are horizon records, not independent trades or a win rate.
- The strategy-learning loop remains active and hypothesis-only; `policy_mutation_enabled=false`, `execution_enabled=false`, `orders_placed=false`. The current strategy report had 13 candidates, zero gate-approved candidates, and 13 gate-rejected candidates. Win rate remains not calculable for approved directional outcomes.

## Protected state and anti-duplication rules
- The working tree at `/opt/hes-trade-agent` is dirty: 13 unstaged changes and 129 untracked paths were reported. **Do not clean/reset/checkout over it, delete untracked files, or use it as a deployment source.**
- Production pointer remains `/opt/hes-trade-agent/current -> releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0`; no pointer switch or service restart was performed in this audit.
- Reuse the existing Gate.io persisted-candle feed, `global_market_data_reader_v1`, `web.dashboard.py` in the staged candidate, existing Signal Agent/Mother/Risk Gate, existing NewsIntelligenceBrain lineage, and existing forward journal/neutral outcome tracker. Do not create a parallel market-data collector, second dashboard, second news engine, second journal, or separate candle/indicator pipeline.
- Market data is from the approved global provider (currently Gate.io Public Spot for BTC_USDT 15m/1h/4h); the selected broker/exchange adapter is a separate execution/order-status/fill boundary. A live chart feed is not execution approval.
- Existing candidate PR #398 remains Draft/open/unmerged according to its latest recorded state; its reported CI success does not itself authorize deployment. News, multi-symbol/multi-market, Mother, execution adapter and journal candidates remain subject to their existing dependency chains and exact-head evidence. Do not merge stacked candidates out of order.

## Next actions — ordered, without repeating completed work
1. Preserve the completed 24h soak evidence and hash/verify the final summary plus sample continuity from the immutable log. Do not restart or rerun the completed soak unless a new acceptance protocol requires it.
2. Re-run read-only dashboard smoke with the exact documented `/api/candles` contract and compare the returned batch hash to `/healthz` and `/api/signal`; record exact HTTP codes and timestamps.
3. Resolve the structure/strategy-quality provider wiring on the existing canonical data path, with tests proving the same closed-candle batch feeds chart and analysis; keep the Risk Gate fail-closed.
4. Complete exact-head and independent review for the existing candidate dependency chain; reconcile PR #398 and its descendants before any release action. Do not bypass required GitHub protection.
5. Finish the existing News Radar integration/continuous monitor candidate using the one NewsIntelligenceBrain, qualify each official source independently, and keep coverage limitations explicit.
6. Treat multi-symbol crypto (ETH/SOL observation candidate) separately from approved BTC strategy scope; other asset classes/venues remain disabled until provider, instrument/calendar/volume semantics and evidence are qualified.
7. Verify concrete execution adapter contracts, symbol/instrument mapping, idempotency, account/order/fill reconciliation, protective orders and paper soak before any owner-approved execution enablement. No live order or deployment is authorized by this checkpoint.
8. Continue the forward NO_TRADE cohort until matured evidence is sufficient; preserve the distinction between rejected-proposal diagnostics, gate-qualified hypothetical outcomes, actual fills and net P&L.

## Safety state
- `execution_enabled=false`
- `orders_placed=false`
- `policy_mutation_enabled=false`
- Release: `HOLD / NO_TRADE_ONLY`
- No secrets or credentials were read, no orders were submitted, no service was restarted, and the production release pointer was not changed during this audit.


## Follow-up exact runtime verification — 2026-10-31

A second read-only verification pass confirmed:
- Gate.io soak sample IDs are exactly continuous from 1 through 1,440; all 1,440 sample records have `ok=true`; elapsed seconds are monotonic; every sample is scoped to `gateio_public_spot / BTC_USDT`; exactly one final `passed=true` summary exists.
- SHA-256 of the completed soak JSONL at verification time: `155d426162ecb301a0423b20f906455f459180f4126017f3da0513844b34788e`.
- The three live dashboard routes returned HTTP 200: `/healthz`, `/api/candles`, and `/api/signal`.
- `/api/candles` returned 240 candles for BTCUSDT / 15m. The batch digest was identical across health, candles, and signal: `80a3c0db66f4d3356887b7b169df255d98037c4e48d2dd5a6d335c30e05fb56c`. This confirms current same-batch identity across these API responses, not browser-render parity.
- The signal endpoint remained `BLOCKED / NO_TRADE`, with `execution_enabled=false`; no order route was called. This is the correct fail-closed result while structure/strategy-quality providers and execution-instrument evidence are absent.
- Latest candle age was approximately 419 seconds during this pass; the API reported the stream disabled. Keep the existing feed/REST freshness contract as the source of truth; do not describe WebSocket as verified live merely because the 24-hour persisted-feed soak passed.

No production code, release pointer, service state, credentials, or order state was changed by this verification. The soak's completion is an evidence milestone, not authorization to merge/deploy or enable execution.


## Follow-up candidate/runtime gate — 2026-10-31 (latest read-only pass)

### Executable milestone completed: exact-head candidate + canonical-journal copy smoke
- Re-verified PR #398 exact head `c4635fbd828e85b067a89b136513eb259b21dff8`; its source archive SHA-256 is `48e02ea47724f8fb9378a872dcfdf6cfc99a67d176601c6170f3786c242ce7f3`.
- Fresh isolated runtime smoke at `/srv/hes-evidence/pr398-c4635fbd828e85b067a89b136513eb259b21dff8-fresh-runtime-smoke-20261031.json`: 9/9 assertions passed; focused candidate tests 107 passed plus 8 subtests. The candidate read only copies of current Gate.io persisted candles; all test writes stayed in temporary locations.
- Separate canonical-journal copy smoke at `/srv/hes-evidence/pr398-c4635fbd828e85b067a89b136513eb259b21dff8-journal-copy-smoke-20261031.json`: all read routes returned 200; candidate read 441 decision records; duplicate polling was idempotent; journal copy grew from 466 to 467 total records for the first event and remained unchanged on repeat; hash-before/after was recorded in the evidence file. This did not write the production journal.
- Same-batch digest was identical across candidate health/candles/signal for each smoke. Mother witness verified, decision stayed `NO_TRADE`, execution authorization false, and `POST /api/order` returned 405 with no order. Candidate rejection evidence included missing pullback/reversal/ADX gates, confirmation quorum not met, strategy quality FAIL, and unverified execution-instrument mapping. Do not weaken these gates to manufacture an entry.
- Evidence JSON SHA-256: fresh smoke `d3bdc14346406837dbabaf1a868f9c7d2ebda2de810c0378960d8ea155450068`; canonical-journal copy smoke `e6c5b0f0128ea5bca033c45a3a18283d657738460fafb14fa44fdfa71c78ce96`.

### Current production runtime recheck
- Existing read-only dashboard and Gate.io 15m/1h/4h services were all `active`.
- Production `/healthz` returned 200, `NO_TRADE_ONLY`, `execution_enabled=false`, source `gateio_public_spot`, reader `global_market_data_reader_v1`, symbol `BTC_USDT`, and input batch SHA-256 `80a3c0db66f4d3356887b7b169df255d98037c4e48d2dd5a6d335c30e05fb56c`. Latest candle age was about 517 seconds at this probe; the runtime reported stream disabled. Continue monitoring freshness; do not call this a verified live WebSocket stream.
- Production `GET /api/journal` still returned HTTP 404. This is the concrete candidate-to-production parity gap; the isolated candidate already passes the route, but production has not been switched.
- Production symlink remains `/opt/hes-trade-agent/current -> releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0`. No pointer change, service restart, code overwrite, credential access, or order was made.

### Current checkout identity correction / workspace protection
- Latest read-only project snapshot reports `/opt/hes-trade-agent` branch `feat/gateio-global-market-data-v1`, HEAD `060d0d36ae61`, dirty with 13 unstaged changes and 129 untracked paths. This supersedes earlier casual references to branch `main` for the current checkout. Preserve the workspace exactly; do not clean/reset/switch branches or deploy from it.
- The host's `vps-second-261930` string is a hostname, not a second VPS. There is still one VPS only.

### Candidate dependency map — review before any release action
- PR #398 (`c4635fbd...`): Gate.io canonical data + dashboard/Signal/Mother/journal candidate; 30/30 recorded CI checks passed, but PR remains Draft/open and production parity is incomplete.
- PR #399 and #404: reuse the existing NewsIntelligenceBrain; #404 adds continuous durable monitoring to close the request-triggered-refresh gap. News coverage remains explicitly partial and must not originate a signal.
- PR #400: ETH/SOL are observation/chart candidates only; BTC remains the only strategy-approved scope. Other asset classes remain disabled pending provider/calendar/volume semantics and evidence.
- PR #401: carries forward the existing venue-neutral ExecutionAdapter contract; no concrete live venue is approved. Gate.io is market-data-only, not an execution authorization.
- PR #402: capability-driven sequence semantics; capabilities stay disabled until exact-scope primary evidence and independent pins exist.
- PR #403: fixes a mocked Gate.io WebSocket reconnect resource leak; mocked fault injection is not a live WebSocket proof.
- These candidates are stacked and must not be merged out of order. Exact-head CI, independent review, the authorized production app/path and outbound policy, protected backup/restore, and release/rollback approval remain gates. No PR status or historical test report by itself authorizes production rollout.

### Next non-duplicative action order
1. Reconcile the exact dependency/base/head chain for #398 → #399 → #404 and the separately scoped #400/#401/#402/#403 candidates; require current exact-head CI and independent review before any merge.
2. Close production `/api/journal` parity only by the reviewed #398 candidate path, using the existing canonical journal and idempotency contract; do not patch in a second journal or deploy the old/dirty checkout.
3. Qualify strategy evidence on the same canonical closed-candle batch. Keep Mother/Risk Gate fail-closed until strategy candidate approval, confirmation quorum, structure, risk geometry, and execution instrument evidence are independently satisfied.
4. Keep News Radar partial/transparent; keep ETH/SOL observation-only and other asset classes disabled until per-scope validation and soak.
5. Complete independent security review and establish an encrypted off-host backup plus tested restore before release; no scanner is currently installed, so no vulnerability-clearance claim is justified.
6. Keep `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`; no production deployment, live order, or execution enablement is authorized by this checkpoint. Target remains 2026-11-19.

## Follow-up execution pass — 2026-10-31: deployment-control boundary and strategy-provider candidate

### New actionable finding: dashboard service is not registered in SentinelX policy
- Fresh SentinelX capability/status check confirms the single host is running SentinelX Core 0.23.34; `hes-readonly-dashboard.service` is NOT in the allowed `services` map. The registered services currently include nginx, docker, sentinelx-cloud-core and hes-strategy-learning-loop.service.
- A read-only `sentinel_service_status` request for `hes-readonly-dashboard.service` returned `service_not_allowed`. This is a control-plane permission blocker, not evidence that systemd or the dashboard itself is down. The active dashboard had previously been verified on loopback port 8765, and the live `/api/journal` route gap remains.
- The policy file `/etc/sentinelx/config.yaml` explicitly documents that an agent must not edit its own policy when the file is outside a writable file_ops path. Do not bypass that boundary with `script_run`, sudo shell tricks, or an unreviewed config mutation. Operator-controlled minimal fix, if approved: add under `services:` a narrowly scoped entry `hes-readonly-dashboard.service: { actions: [status, restart] }`, then restart `sentinelx-cloud-core` from the approved service control path and re-check capabilities/status. Do not add `stop`, `start`, or broad commands. Until the operator makes that policy change, dashboard service restart/status via SentinelX is blocked by design.

### Current strategy-provider candidate is PR #394, not a new engine
- PR #394 (`8e31d65939c16ed35eb0e7b44274b7ac5670525e`) is the more relevant strategy-provider candidate on the Gate.io canonical path. It explicitly uses Gate.io Spot BTC_USDT/15m, the existing `ForwardJournalV1` and `trade_journal_v2.jsonl`, and removes an unused parallel learning-loop report engine. It is a stacked candidate based on PR #383 and is 96 commits ahead of its base and 211 commits ahead of `main`; it must not be retargeted or merged directly into main.
- PR #394 exact-head CI evidence: full repository suite **643 passed + 24 subtests** (run `41023654434`), dashboard/native single-path PASS (`41023654430`), browser render PASS (`41023654546`), bounded WebSocket smoke PASS (`41023654427`). The WebSocket smoke is bounded only, not a 24-hour live Gate.io stream soak. Isolated replay verified same-batch identity, idempotent append, no inferred outcomes, and no execution; production route parity and release are still pending.
- PR #394 has **no submitted reviews** at this check. PR #398 also has comments/evidence but no approval review. A source/test pass is not an independent review. Do not merge either branch or duplicate-merge ancestor candidates.
- PR #399 continues the existing NewsIntelligenceBrain on top of #398; it is stacked and does not have independent actions until its base is accepted. PR #359 is a separate parallel news component and must not be combined with #399; reuse the integrated path, do not create a second news engine.

### Required next order, updated to avoid duplicate work
1. Keep Gate.io Public Spot BTC_USDT as the single chart/candle/analysis source; exchange/broker adapters remain a separate execution path. Do not add Binance or Tabdeal as competing live analysis feeds.
2. Reconcile and review the parent chain before release: #383 → #388/#398 lineage → #394 strategy-provider superset, with #399/#404 news integration and #401 execution contract only after the correct base is accepted. Avoid merging both an ancestor and its superset independently. Confirm exact current head and CI after every base update.
3. Resolve the SentinelX service policy through an operator-approved minimal config change, then verify service registration and the current production route behavior. Do not bypass SentinelX policy from a script.
4. Close the production `/api/journal` gap using the existing canonical journal, only after independent review and an explicit release/rollback gate; no second journal and no deployment from the dirty checkout.
5. Keep strategy, confirmation, risk, and instrument mapping fail-closed. The current `NO_TRADE` remains correct until independent evidence qualifies an entry; Gate.io data feed does not authorize Gate.io execution.
6. Keep news partial and veto/context-only; ETH/SOL observation-only; other asset classes disabled. Require per-scope evidence before promotion.
7. Before any release, complete independent review, protected encrypted off-host backup plus restore drill, security review, and production rollback verification.

### State unchanged
- No policy file was edited; no service was restarted; no release pointer or production journal was changed; no credentials were accessed; no order was submitted.
- Current disposition remains `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`, `execution_enabled=false`, `orders_placed=false`. Target delivery remains 2026-11-19.

## Follow-up execution pass — 2026-10-31: fresh runtime + independent-review audit

### Fresh read-only production probe
- Dashboard unit remains active and the production pointer is still `/opt/hes-trade-agent/releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0`.
- `GET /healthz`: HTTP 200; `status=ok`; `NO_TRADE_ONLY`; `execution_enabled=false`; Gate.io Public Spot / `global_market_data_reader_v1` / BTC_USDT; current batch SHA-256 `1332ea109566ecce12298d77ccaabff01ea5da7a50cbc11c2fdc923e3f68a21c`; reported latest candle age about 36 seconds.
- `GET /api/candles`: HTTP 200; 240 BTCUSDT 15m candles; same batch SHA-256 `1332ea109566ecce12298d77ccaabff01ea5da7a50cbc11c2fdc923e3f68a21c`.
- `GET /api/signal`: HTTP 200; `BLOCKED / NO_TRADE`; same batch SHA-256. Remaining explicit blockers include structure direction/validated structure provider, strategy-quality provider not wired, HTF/pullback/reversal/MFI/ADX confirmation evidence, 3:1 risk geometry, and execution instrument mapping evidence. Do not weaken these gates.
- `GET /api/journal`: HTTP 404 `not_found`. The production candidate-parity blocker remains unresolved.
- Exact installed Gate.io units: `hes-global-market-data-gateio.service`, `...-1h.service`, and `...-4h.service` are active; the completed `...-soak.service` is inactive/dead as expected after successful completion. The generic `...-15m.service` name used in an earlier probe was not an installed unit; do not record it as a failed feed. The active generic Gate.io unit plus fresh persisted candles and the 24h soak remain the evidence. No WebSocket-live claim.
- Worktree remains dirty; no cleanup/reset/branch switch was attempted. No service restart, release-pointer change, journal write, credentials access, or order occurred.

### PR independent-review audit
- Re-queried submitted reviews for PRs #383, #388, #394, #398, #399 and #404.
- #383, #388, #394, #399 and #404 have zero submitted reviews in the current review listing.
- #398 has four submitted review records, all authored by the repository owner and all state `COMMENTED`; none is an independent approval. Evidence comments do not satisfy independent review.
- Therefore the stacked parent chain still lacks independent review. No merge, retarget, or release action is justified. Preserve dependency order and reconcile the chain only after an independent reviewer is available.

### Current disposition
- `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`; execution OFF; no production deployment.
- Remaining hard blockers: independent review of the correct stacked parent chain; production `/api/journal` parity via the reviewed existing canonical-journal candidate; validated structure/strategy-quality providers and complete confirmation/risk evidence; execution venue/instrument proof; approved SentinelX policy registration for dashboard status/restart; protected encrypted off-host backup and tested restore; independent security review.
- Delivery target remains 2026-11-19. Continue from this checkpoint without rebuilding existing components or repeating the completed 24-hour soak.


## Follow-up architecture/dependency correction — 2026-10-31

### Exact PR ancestry verified from GitHub metadata and commit comparison
- PR #383: `fix/dashboard-persisted-global-feed-20261025` based on `fix/gateio-base-volume-contract-20261025`; head `bf6627571802f2d1aaac930dc22fb6437b11ac04`.
- PR #388: `integration/gateio-persisted-feed-signal-agent-20261026` based on PR #383 head; head `2e8d3859ef154b030e0965ad4479f3fad36ae4c0`. This is exactly the commit currently selected by production `current`.
- PR #394: `fix/gateio-strategy-evidence-scope-20261028` based on PR #383 head; head `8e31d65939c16ed35eb0e7b44274b7ac5670525e`. GitHub commit comparison confirms #388 head is an ancestor of #394 and #394 is 61 commits ahead of #388. Therefore #394 is the natural strategy-provider continuation of the #388 runtime lineage.
- PR #398: `consolidated/gateio-dashboard-signal-agent-v1` based on `main`, head `c4635fbd828e85b067a89b136513eb259b21dff8`. It is a separate consolidated branch, not a simple child of #394. Exact comparison #398-head → #394-head reports diverged (211 commits ahead, 12 behind); do not merge #398 and #394 as if they were consecutive or combine by blind cherry-pick. Select and review one canonical lineage; existing #388 → #394 is closest to the live deployed base, while #398 is a separately tested consolidation candidate.
- PR #399 is based on #398 head (base SHA `268fa7524c12e085d010437bf50bdb163fa7277a`); PR #404 is based on #399 head (base SHA `f162978ed32744296c02fb37b4f1babaf843ffa8`). These news candidates therefore belong to the #398 lineage and must not be stacked onto #394 without a reviewed integration/rebase.
- All six PRs (#383/#388/#394/#398/#399/#404) remain open and Draft at this check. None has an independently requested reviewer recorded. Review listing: #383/#388/#394/#399/#404 have zero submitted reviews; #398 has four COMMENTED submissions by the repository owner only, no independent approval.
- Fresh GitHub Actions query for exact #394 head reports four completed successful workflows: Gate.io Dashboard Full Repository Regression; Native OHLCV WebSocket Live Smoke v1; Native OHLCV Dashboard Single Path v1; Native OHLCV Browser Render Smoke v1. The WebSocket workflow is bounded smoke, not proof of a continuous live stream.

### Production journal route gap — root cause narrowed
- Read-only inspection confirms the active dashboard process PID 83194 has WorkingDirectory and PYTHONPATH `/opt/hes-trade-agent/current`, and the current symlink resolves to release `2e8d3859ef154b030e0965ad4479f3fad36ae4c0` (PR #388 head). The production release's `web/dashboard.py` does not contain an `/api/journal` route; this directly explains production HTTP 404.
- The isolated PR #398 candidate source does contain `/api/journal` and reads the existing canonical `trade_journal_v2.jsonl` through `configured_decision_journal`; its existing tests cover the route and fail-closed behavior. It is candidate evidence only, not production parity. The live canonical journal exists (about 2.2 MB); it was not opened for content, modified, copied, or exposed in this pass.
- The active dashboard systemd unit uses `/opt/hes-trade-agent/current`, but its current policy is not registered in SentinelX's allowed services map. Do not restart it until the operator-approved minimal `status,restart` policy registration is in place. No systemd, SentinelX policy, or runtime change was made.
- No deployment was performed. A safe fix requires selecting the canonical lineage, independent review, exact-head revalidation, approved SentinelX control, backup/rollback gate, then an explicitly approved release switch. Do not patch the old release in place.

### Fresh operational state
- Dashboard PID 83194 remains active on loopback; production symlink remains at #388 head.
- Current health/candles/signal batch hash remains `1332ea109566ecce12298d77ccaabff01ea5da7a50cbc11c2fdc923e3f68a21c`; 240 closed BTCUSDT 15m candles; reported latest age ~36 seconds at the probe. Signal remains BLOCKED/NO_TRADE.
- Gate.io candle units `hes-global-market-data-gateio.service`, `...-1h.service`, and `...-4h.service` are active. The completed soak unit is inactive/dead as expected. The previously referenced exact unit name `...-15m.service` is not installed; do not treat this naming mismatch as a data-feed outage.
- Working tree remains dirty and protected; no reset/checkout/cleanup, service restart, pointer change, journal mutation, credentials access, or order occurred.

### Decision
- Prefer the #388 → #394 lineage for further technical work because it extends the exact deployed #388 base and has the strategy-provider change; keep #398/#399/#404 as a separate consolidation/news branch requiring explicit reconciliation, not as a merge target for #394.
- Hard gates remain independent review, operator-approved SentinelX service permission, production journal route release, structure/strategy quality and risk validation, execution instrument evidence, off-host encrypted backup/restore, and security review.
- Disposition remains `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`; target 2026-11-19.


## Forward execution step — 2026-10-31: journal candidate exercised against real canonical data (read-only)

### Exact PR #394 journal projection verification
- Retrieved exact-head source `8e31d65939c16ed35eb0e7b44274b7ac5670525e` for the existing `forward/trade_journal_view_v1.py`, `learning_evidence_adapter_v1.py`, and `forward_journal_v1.py`; no new engine or journal was created.
- Ran the exact PR #394 projection implementation on the production canonical file `/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl` in read-only mode. Result: `VERIFIED`, 486 total records, 460 directional/NO_TRADE decision records, first 5 projected rows returned. The projection does not infer outcomes and keeps execution disabled.
- Before/after journal SHA-256 was identical: `d4a6ccc03f8d6a7b0e9d17e856dca68f5b6f54df79345daa885b43cb689b6d20`; file size 2,197,141 bytes. No event was appended or modified.
- Ran the exact PR #394 `tests/test_trade_journal_view_v1.py` in an isolated temporary directory using the existing project virtualenv and exact source files. Result: **6 passed**. The first attempt with system Python failed because pytest is not installed there; the second, using `/opt/hes-trade-agent/.venv/bin/python`, passed. No dependency was installed.
- Verified the existing journal writer's idempotency key is derived from symbol/timeframe/source/product + 15m batch hash + 4h batch hash + policy version. Repeated identical evidence returns `ALREADY_RECORDED`; changed evidence for the same event fails closed. This prevents dashboard polling from duplicating the same closed-candle decision.
- This is an actual source-on-production-data compatibility proof, not yet production HTTP route parity; current production `/api/journal` still returns 404 until a reviewed release is approved.

### Service access / sandbox compatibility
- Current dashboard runs as `sentinelx:sentinelx`. The existing canonical journal and its lock file are owned by that user; both are readable and writable at the Unix permission layer.
- Current systemd unit has `ProtectSystem=strict` and marks `/opt/hes-trade-agent/data/forward` read-only, with no `ReadWritePaths`. Therefore the new Signal Agent append path in PR #394 would be denied by systemd sandbox unless the reviewed unit adds only the two narrow exceptions for the existing journal and its existing lock file. Exact PR #394 unit already expresses those narrow `ReadWritePaths`; it does not grant broad write access to the data directory.
- Current `/etc/sentinelx/config.yaml` service allowlist includes `sentinelx-cloud-core` and `hes-strategy-learning-loop.service`, but not `hes-readonly-dashboard.service`. Existing policy playbook explicitly says not to self-edit the agent's own policy. Required operator change is only:
  ```yaml
  hes-readonly-dashboard.service:
    actions: [status, restart]
  ```
  Add under `services:`; do not add start/stop. After operator makes that change, restart `sentinelx-cloud-core` through its already-allowed service control and verify the dashboard service status. No policy edit or service restart was performed in this pass.
- Candidate systemd unit also requires the existing journal and lock file to exist; both currently exist. No chmod/chown or other permission changes were needed.

### Decision / next gate
- The existing PR #394 journal projection and idempotent writer are compatible with the current real journal and pass all six focused tests. This is a strong integration candidate and avoids rebuilding the journal/Learning Loop.
- Still no production route parity, no independent PR review, no operator policy authorization, no systemd release switch, and no execution approval. Keep `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`; no live order.


## Deep-review decision and next execution sequence — 2026-10-31

### What is now re-confirmed
- PR #394 exact head remains `8e31d65939c16ed35eb0e7b44274b7ac5670525e`; PR is open, Draft, and GitHub reports mergeable, but mergeability is not approval.
- Four exact-head Actions runs independently fetched from GitHub are completed/successful:
  - Full repository regression: 41023654434
  - Native OHLCV Dashboard Single Path: 41023654430
  - Native OHLCV WebSocket Live Smoke: 41023654427
  - Native OHLCV Browser Render Smoke: 41023654546
  The WebSocket run is bounded smoke, not a 24-hour soak.
- PR body reports full repository regression 643 passed + 24 subtests; exact-head Actions conclusion was independently checked. This does not replace a human code review.
- PR #394 explicitly preserves Gate.io Spot BTC_USDT as the single canonical analysis/chart source, uses one persisted batch for chart and Signal, and keeps execution separate/disabled. Dashboard contains no order endpoint; POST is rejected and unsupported order path returns 404 in tests.
- PR #394 writes Signal decisions to the existing canonical `trade_journal_v2.jsonl` and projects that same journal without inventing outcomes. Runtime compatibility and focused tests are now independently verified above.
- Current production dashboard remains the #388 release. Its `/api/journal` route is absent (404), so journal UI/API is not yet in production. This is a release integration gap, not evidence that the journal file or Learning Loop is missing.

### Correct priority — do not jump to deployment
1. **Close review/release governance first:** obtain an independent human reviewer for PR #394 and explicit owner/operator approval for the narrow SentinelX service allowlist entry. No reviewer identity is known; do not fabricate one or self-approve.
2. **Prepare a controlled release candidate, isolated from the dirty checkout:** verify exact SHA and provenance, preserve the current release as rollback, check systemd unit diff, and preflight the journal/lock file. Do not overwrite `current`, reset the dirty worktree, or restart services before the release gate.
3. **Deploy only after gates 1–2:** use a new immutable release directory; install only the reviewed PR #394 files; apply its narrow journal/lock `ReadWritePaths`; add the dashboard service allowlist only after operator edit; restart only the dashboard through the now-allowed status/restart policy. Verify `/healthz`, `/api/candles`, `/api/signal`, `/api/journal`, matching source/batch hashes, journal idempotency, and service sandbox. Keep loopback-only.
4. **Complete forward-only counterfactual evaluation:** connect the already-existing no-trade outcome tracker to the canonical journal/Learning Loop, preserve entry-time snapshots, compare hypothetical LONG/SHORT outcomes with fees/slippage/funding and a predeclared horizon, classify prevented loss vs missed opportunity vs indeterminate, and never infer outcome from future data without a timestamped evaluation record. Existing PR #394 journal projection intentionally does not claim this outcome validation is complete.
5. **Only then address execution adapter:** first establish a separate execution contract and instrument mapping proof for the chosen exchange/broker (Tabdeal is the initial target, subject to verified API behavior). Test precision, min notional, leverage, position mode, order idempotency, partial fills, cancel/replace, reconnect reconciliation, and kill switch in paper/test environment. No exchange candles may replace Gate.io analysis candles. No live order until separately authorized.

### Hard blockers that require operator/reviewer input
- Add under `services:` in `/etc/sentinelx/config.yaml` only:
  ```yaml
  hes-readonly-dashboard.service:
    actions: [status, restart]
  ```
  Do not grant start/stop. Agent must not edit its own SentinelX policy.
- An independent reviewer must be nominated/requested by the repository owner; self-authored comments or CI cannot satisfy independent review.
- Production release/rollback authority and later execution authorization remain separate decisions.

### Current disposition
**Proceed with isolated release preparation and forward-only evaluation design; do not merge, deploy, restart, enable order execution, or place trades yet.** The correct next technical move is to prepare a SHA-pinned immutable #394 release package and rollback manifest without touching the active release or dirty worktree. HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY remains mandatory.


## Forward execution pass — 2026-10-31: exact PR #394 release package and rollback preflight

### Exact-source package and immutable release verification
- Downloaded the GitHub source archive for exact PR #394 head `8e31d65939c16ed35eb0e7b44274b7ac5670525e` to `/srv/hes-evidence/pr394-8e31d65939c16ed35eb0e7b44274b7ac5670525e-source.tar.gz`.
- Source archive SHA-256: `0558057918f2e5867a16c7d41b0d777f49c4d95061549dabc237f1901f72f983`.
- Compared every one of the **507 files** in the exact GitHub archive against the already-present immutable candidate directory `/opt/hes-trade-agent/releases/8e31d65939c16ed35eb0e7b44274b7ac5670525e`: **0 missing, 0 mismatches**. The directory is root-owned and mode 0555. This establishes the directory's source-content identity with the exact PR archive; no source files were modified.
- Verified the candidate systemd unit's Git blob SHA matches the exact GitHub file blob SHA `8ea89d284b3c76ba6827a0b8133d113a54e6f985`. It adds only the explicit canonical journal path and its pre-created lock file as narrow `ReadWritePaths`; it does not make the whole forward-data directory writable.
- Exact archive test execution in a temporary extraction, using the existing project virtualenv: **643 passed, 24 subtests passed**. Focused canonical journal projection test: **6 passed**. No dependencies were installed and no repository checkout/worktree was reset or cleaned.
- The earlier direct pytest attempt against the immutable release path without setting the project root on `PYTHONPATH` failed during import and attempted to create pytest cache files in the read-only release. It made no source changes. The correct exact-archive run above passed; cache was disabled and the temporary extraction was removed.

### Rollback preflight artifacts created
- Saved the current dashboard systemd unit as `/srv/hes-evidence/20261031-pr394-predeployment-current-dashboard.service.rollback`; SHA-256 `c8bcf9639a4fb4ad0847e5c8c9d19b2181cd7cca1d685d610327d89a436c3fe9`.
- Created `/srv/hes-evidence/20261031-pr394-predeployment-release-rollback-manifest.json` with exact candidate SHA/archive checksum, current immutable release pointer, current unit checksum and backup path, canonical journal snapshot hash/size, endpoint status, and explicit authorization flags. Manifest SHA-256: `4123bee5e16f037637bdfad5f44421c03733de7ecd8f56d6d63c8aa3fa8d5f9c`.
- Canonical journal snapshot at manifest time: SHA-256 `3a307d9b7afc6412d0055bb61541f6701d3b53517a96eccd4c0084fa51d3b137`, 2,202,407 bytes. This pass did not write to the journal; the snapshot is a time-specific rollback/audit reference, not a static file guarantee.

### Fresh production state after preparation (read-only)
- Current pointer remains `/opt/hes-trade-agent/releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0` (PR #388); dashboard service active.
- `/healthz` HTTP 200; `/api/candles` HTTP 200; `/api/signal` HTTP 200 with `BLOCKED / NO_TRADE`; `/api/journal` HTTP 404. Execution remains disabled.
- No current symlink change, systemd unit installation, service restart, SentinelX policy edit, PR merge, journal write, credential access, or order submission occurred.

### Remaining operator/reviewer gates
- PR #394 remains open/Draft and has no submitted independent reviews. The full test pass and source identity check do not replace independent human review.
- SentinelX's active service policy still does not permit `hes-readonly-dashboard.service`. Only the operator can approve adding under `services:`:
  ```yaml
  hes-readonly-dashboard.service:
    actions: [status, restart]
  ```
  Do not grant start/stop and do not self-edit SentinelX policy.
- After independent review and the operator policy edit, a separate explicit release approval is still required before switching `current` and restarting the dashboard. Execution authorization remains a distinct later decision.

### Disposition
The exact PR #394 source package is now checksum-pinned, its pre-existing immutable release directory is proven byte-for-byte equal across all 507 archive files, the exact-head test suite passes, and a local rollback manifest/unit backup are prepared. This is release preparation, **not deployment**. Preserve `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`; do not merge, deploy, restart, enable execution, or trade until the independent review and operator/release gates are satisfied.
