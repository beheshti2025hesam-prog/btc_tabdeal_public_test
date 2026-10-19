# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-19  
**Disposition:** HOLD / NO_TRADE_ONLY  
**Operating model:** Memory = project map; GitHub = technical source of truth; Chat = conversation log.

## Governing project DNA
- Reuse existing official exchange, broker, and chart-platform capabilities first (native candles/OHLCV, chart APIs, TradingView-compatible feeds where appropriate); optimize or integrate only when a demonstrated requirement is unmet. Do not rebuild an existing capability without evidence of a material gap.
- Candlestick/chart availability is independent of trade-sequence semantics. Do not make sequence research a blocker for ordinary chart/candle use; investigate sequence only when a required feature actually depends on event identity, replay, loss detection, or ordering.
- Keep the design simple and add only decision-critical checks.
- Treat sequence-like fields as opaque unless evidence defines exact venue/product/endpoint/channel/message scope and the required identity/order/continuity guarantees.
- Separate exact-payload replay from repeated opaque values; never infer missing events from numeric gaps without an explicit continuity contract.
- Fail closed on stale, malformed, contradictory, corrupt, or unauthenticated evidence.
- No promotion based only on a green dashboard. Exact-head tests, evidence lineage, and independent review are separate gates.

## Exact-head CI/review audit performed 2026-10-19
Repository default branch inspected at `4956cf519c445edd004fdd4e763bdb3347a7ada9`.

| PR | Exact head | Observed Actions runs | Result | Review state / caveat |
|---|---|---:|---|---|
| #245 opaque Tabdeal sequence | `e5e7e657af43ddb8b6e8152cf08d51850f01d687` | 26 | All returned runs completed successfully | No submitted reviews. Branch is behind current main by 19 commits; synchronize/rebase and rerun exact-head CI before promotion. Production registry pin remains deliberately unset and checked-in evidence registry is empty/unpinned. |
| #318 master checkpoint | `f3d8c1c12fe989d195b89131b56c88bc45edc92d` | 26 | All returned runs completed successfully | Draft documentation PR; does not itself close technical gates. |
| #325 operating principles | `ff780a2b2f41f41de833408156b6a46ad218c100` | 26 | All returned runs completed successfully | Draft documentation PR; no independent review evidenced. |
| #327 Binance native OHLCV | `264ad62f51dee485c8ab9e1053631929c6379e4b` | 27 | All returned runs completed successfully, including Native Binance OHLCV Adapter v1 run 39218587582 | Adapter is Binance-only, read-only. Its five-candle Spot `klines` vs `uiKlines` match is a smoke check, not Tabdeal chart acceptance or full raw HTTP capture. |
| #328 stale Tabdeal WebSocket callbacks | `f1536f39f48f81e04e5a6e9c70e5b25bc9c5e700` | 26 | All returned runs completed successfully, including Forward Integration Verification v1 run 39220590616 | Tests cover delayed callbacks after reconnect and after disconnect. No submitted independent review evidenced. No collector activation or deployment. |

The combined commit-status endpoint returned no status entries for these heads; the counts above refer to completed GitHub Actions runs returned by the workflow-runs endpoint. For #328, the exact-head Forward Integration job completed successfully; the separately named Wallex session-isolation workflow run 39211895824 is from an earlier commit and is not misrepresented as exact-head evidence.

## Latest verified rerun (2026-10-19)
- On PR #320 exact evidence commit `b490611636cca6d133ba9f9cc08d5d9d6333628b`, reran the read-only live probe and deterministic adapter tests. Both jobs completed successfully.
- Fresh probe at 08:48 UTC: `GET /v1/udf/history?symbol=BTCUSDT&resolution=1`; 9 candles covering 08:39–08:47 UTC, latest closed candle age 17.13 seconds, no observed timestamp gaps, one request attempt.
- Raw response SHA-256: `27be8fc0917be0f94f83c8be33542a7db7c071eefe8917ec2d74fdfaee89998d`. Evidence artifact ID `12172749525`; artifact SHA-256 `fbb98056b12d4c3e6bae1034e13f466791f3034a725e084b15b0f69cd402f462`.
- Interpretation remains narrow: current public endpoint reachability and closed-candle delivery only. It does not establish a production freshness SLA, independent rendered-pixel parity, volume semantics, or trading readiness.

## Native-candle-first decision update (2026-10-19)
- Repository audit found an existing read-only native Wallex OHLCV adapter in PR #320 at exact head `b490611636cca6d133ba9f9cc08d5d9d6333628b`, using the official `GET /v1/udf/history` endpoint and the same UDF-style datafeed that the inspected Wallex chart frontend calls for `getBars`.
- PR #320's exact-head GitHub Actions list returned 27 completed runs with success and zero reported failures, including `Native Wallex OHLCV Candle-First Verification` run 39147253717. This is CI evidence, not deployment authorization.
- The pinned 2026-10-18 evidence records source-level chart datafeed parity and numeric OHLC parity for BTCUSDT at 1m (180 common timestamps) and 1h (24 common timestamps), with zero OHLCV mismatches/no gaps and identical raw response hashes for the cited same-window captures. No independent rendered-pixel screenshot was captured.
- The unresolved UDF volume discrepancy is decision-critical only for volume-dependent features: across 99 covered closed bars, UDF `v` was exactly 2x summed public trade quantities. Do not normalize/halve it without authoritative clarification. Price/OHLC candle availability itself does not require trade-sequence reconstruction.
- Therefore use the existing native candle path for candle-dependent HES work; keep sequence semantics as a separate conditional gate only for features requiring trade-level event identity/replay/loss detection/order. Do not rebuild candles from individual trades just to solve sequence semantics.
- PR #320 remains Draft/unmerged, with no submitted independent review. Do not wire it into production or lift HOLD based on CI alone.

## Fresh native-candle endpoint recheck (2026-10-19 08:48 UTC)
- Re-ran only the read-only public-endpoint job on PR #320's exact evidence commit `b490611636cca6d133ba9f9cc08d5d9d6333628b`; deterministic tests also remain green. Both jobs completed successfully on the rerun.
- Fresh probe: `GET /v1/udf/history?symbol=BTCUSDT&resolution=1`; retrieved 9 candles spanning 2026-10-19 08:39–08:47 UTC, latest closed candle age 17.13 seconds, no observed timestamp gaps, one request attempt, raw response SHA-256 `27be8fc0917be0f94f83c8be33542a7db7c071eefe8917ec2d74fdfaee89998d`. Evidence artifact ID `12172749525` (921 bytes; artifact SHA-256 `fbb98056b12d4c3e6bae1034e13f466791f3034a725e084b15b0f69cd402f462`).
- This confirms current read-only endpoint reachability and recent closed-candle delivery at the probe time; it does not establish an approved freshness SLA, rendered-pixel parity, volume semantics, production collector health, or trading readiness.
- Operational choice: native candle/OHLC-based features may be developed against this existing path without trade-sequence reconstruction. Until Wallex clarifies the 2x UDF-volume discrepancy, volume-dependent features must remain gated; never silently halve volume or treat a green probe as approval to deploy.

## Technical conclusions
1. **Stale callback isolation:** PR #328 ties callbacks to the exact active socket object, revokes the active session before close, and guards frame normalization/handoff under a lock. Its deterministic tests inject prior-session `on_message` and `on_open` callbacks while a newer session is active and callbacks after disconnect; expected result is rejection with no downstream record.
2. **Sequence semantics:** PR #245 preserves native integer/string identity and requires a reviewed three-part evidence bundle (sequence contract, source completeness, source ordering). The code may stay fail-closed, but this PR must be synchronized with current main and independently reviewed before any promotion. Never pin a production registry using CI fixtures or self-attested evidence.
3. **Native OHLCV:** PR #327 preserves Decimal values, raw response hash, retrieval time, candle timestamps, and gaps; open candles are excluded. It does not establish Tabdeal's official native OHLCV endpoint/schema. Do not wire Binance data into Tabdeal strategy context.
4. **Principle documentation:** PR #325 records the resource-first/minimal-complexity rule. It remains a draft and should be reviewed/merged through normal controls, not treated as a runtime gate closure.
5. **CI recovery:** No failures were returned in the observed exact-head run sets. This is not a claim that every required external acceptance gate passed.

## Remaining blockers (do not silently close)
- No independent human review is recorded for PRs #245, #327, or #328.
- PR #245 is 19 commits behind current main and must be synchronized; then rerun exact-head tests and review the resulting diff.
- Production evidence-registry pin remains unset/empty; source-completeness and ordering/recovery semantics for Tabdeal `trade.sequence` remain unproven. This blocks only features that rely on those semantics, not ordinary candle/chart use.
- Additional source inspection found `SourceEvidenceRegistryV1.resolve()` currently raises `SOURCE_EVIDENCE_REVIEW_PROVENANCE_UNVERIFIABLE` unconditionally after byte/scope checks; there is no authenticated review-record verifier/happy path. This is fail-closed (safe), but means a future registry pin alone cannot enable acceptance. Do not remove the guard without implementing and independently reviewing authenticated reviewer provenance.
- The SEQ-001…016 ledger on the research branch marks only some vectors mapped, many blocked, and scenario-level execution unverified; generic green workflows must not be counted as complete vector coverage.
- The exact-head workflow list for PR #245 did not include its dedicated `Opaque Tabdeal Sequence Evidence v1` job. Run 38420800963 passed that workflow on an older SHA (`f4bf19cb48c86a1f8fbaef7ea4afeb811773c9fd`), which is not transferable to current PR head `e5e7e657af43ddb8b6e8152cf08d51850f01d687`.
- Official Tabdeal native OHLCV endpoint/schema and same-chart parity remain unverified. Binance adapter is not a substitute.
- Wallex OHLCV research remains blocked for volume-dependent promotion: UDF volume was observed at exactly 2x summed public trade quantities across 99 closed bars; do not halve/normalize without authoritative clarification. Official Socket.IO transport reachability and production collector integration also remain unverified.
- No production-like crash/restart proof, forward observation acceptance, deployment authorization, or execution authorization is established by these CI runs.

## Next actions, forward-only
1. Identify the exact target chart/product/timeframe and inspect existing official/native candle endpoints or supported chart feeds first; compare closed candles only where parity is required, matching symbol/timeframe/timezone and retaining raw bytes plus SHA-256.
2. Treat PR #245 and SEQ-001…016 as a separate, conditional workstream: map vectors to named deterministic/property tests only for features that genuinely depend on sequence semantics. Do not let this workstream block ordinary candle/chart integration.
3. Synchronize PR #245 with current main only when its sequence-dependent functionality is needed; preserve its current branch and evidence without force-resetting user work.
4. Request independent review for #245, #327, and #328; do not self-approve.
5. Preserve `HOLD / NO_TRADE_ONLY`; no collector activation, deployment, account mutation, orders, or trading until all required gates pass.

## Provenance
- PR #245: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/245
- PR #318: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/318
- PR #325: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/325
- PR #327: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/327
- PR #328: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/328


## Follow-up completion pass (2026-10-19)
- **Native Tabdeal candle endpoint research:** inspected the current official API documentation at https://docs.tabdeal.org/ (retrieved via the official docs page). Its documented Spot market surface includes depth, recent trades, exchange info, and WebSocket order-book topics; the FAPI surface includes aggregate depth and depth/trade WebSocket feeds. Searches of the official document for `kline`, `OHLC`, `candlestick`, and Persian `کندل` found no candle-history endpoint or documented OHLCV schema. This is a documentation-scope finding, not proof that the Tabdeal website frontend has no private/undocumented chart datafeed. No unsupported endpoint was invented and no candles were rebuilt from trades.
- **Decision for ordinary candles/charts:** continue to use an already-supported native exchange/chart datafeed when one is identified and verified. PR #320's Wallex UDF history path is an existing read-only native-candle implementation; it is not evidence for Tabdeal. PR #327's Binance klines adapter is Binance-only and must not be substituted into Tabdeal market context. Exact Tabdeal chart/product/timeframe parity remains unverified until the actual target chart/feed is inspected and captured.
- **Sequence workstream disposition:** no sequence dependency is demonstrated for ordinary OHLCV/chart availability, so PR #245 is intentionally **not synchronized or expanded in this pass**. This preserves its existing branch/evidence and avoids turning sequence semantics into an artificial candle blocker. Revisit PR #245 only if a specific required feature needs trade identity, replay, loss detection, or event ordering.
- **Independent review request status:** PRs #245, #327, and #328 remain without submitted reviews. No independent reviewer identity was established from the available PR metadata; no reviewer was guessed, self-requested, or self-approved. The review gate remains open and requires a real eligible human reviewer.
- **Safety posture unchanged:** `HOLD / NO_TRADE_ONLY`; no production registry pin, collector activation, deployment, account mutation, or trading. Wallex's unresolved 2x UDF-volume discrepancy continues to gate only volume-dependent features, not ordinary price/OHLC candles.


## Explicit continuation checkpoint (2026-10-19)
- Resume from this exact state; do not restart completed discovery or re-create existing components.
- **Repository truth:** `beheshti2025hesam-prog/btc_tabdeal_public_test`. Prior recorded checkpoint commit: `bf6266ea059d1167a2c5dec4a24c9d08b7b829d9`.
- **Next concrete task:** verify the actual Tabdeal website chart's network datafeed (symbol, market/product, timeframe, timestamps, OHLCV schema) and compare it with an authoritative/native source if available. Do not infer a public candle endpoint from missing docs; do not build candles from individual trades as a workaround unless a specific, evidenced requirement makes that necessary.
- **Reuse-first rule:** prefer existing exchange/broker/chart-platform capabilities and already-built adapters. Optimize only demonstrated gaps. Keep Wallex and Binance adapters scoped to their own venues; neither proves Tabdeal parity.
- **Sequence is conditional:** ordinary chart/candle/OHLC access does not require solving trade-sequence semantics. Resume sequence investigation only for a named requirement involving trade identity, ordering, replay, or loss detection.
- **Open gates:** Tabdeal chart-feed/parity evidence; independent eligible review for PRs #245, #327, #328; clarify Wallex's 2x UDF volume discrepancy before enabling volume-dependent logic. Do not guess a reviewer or silently normalize volume.
- **Safety:** maintain `HOLD / NO_TRADE_ONLY`; no merge/deploy/production collector activation/trading without the required evidence and independent review.

## Resume marker — saved 2026-10-19
This marker records the exact stopping point requested by the project owner. It does not claim any additional technical investigation was performed after the preceding checkpoint.

- **Stop point:** official Tabdeal API documentation has been checked; it does not document a candle-history/OHLCV endpoint in the inspected surface. This does **not** establish that the live Tabdeal website chart lacks an undocumented/private feed.
- **Next action on resume:** inspect the real Tabdeal website chart's network requests/datafeed for the exact market/product and timeframe; capture endpoint, request parameters, response schema, timestamps, and raw evidence/hash. Reuse a native or existing chart feed if one is verified. Do not invent an endpoint or reconstruct candles from trades without a demonstrated requirement.
- **Do not repeat completed work:** do not restart the documented API search, re-create the existing Wallex/Binance adapters, or expand sequence research as a prerequisite for ordinary candles. Wallex and Binance evidence is venue-specific and cannot prove Tabdeal parity.
- **Still open:** Tabdeal chart-feed/parity verification; eligible independent reviews for PRs #245, #327, and #328; authoritative explanation of Wallex's observed 2× UDF-volume discrepancy before any volume-dependent feature is enabled.
- **Hard safety boundary:** `HOLD / NO_TRADE_ONLY`. No production activation, deployment, account mutation, orders, or trading without the applicable evidence and independent review.
- **Project DNA reminder:** reuse existing capability first; integrate/optimize only a proven gap. GitHub is technical truth, this Master Checkpoint is the project map, and chat is the conversation log.


## Follow-up execution review — 2026-10-19 15:20 UTC+03:30

### Reuse-first native candle integration review
- Reviewed the existing stacked implementation rather than creating another adapter or candle engine:
  - PR #329 bridge head `70a3949a2b512dead8b00ec57c92c91d2c103862`: its returned Actions runs completed successfully; the bridge reuses the existing candle model and native adapter-shaped contract.
  - PR #330 adapter-to-bridge contract head `ec76f51dc6511603ad429e21ebea874d51238cd0`: exact-head run `39238891378` succeeded. The PR records 6 offline parser-to-bridge tests against pinned Wallex and Binance adapter revisions.
  - PR #331 native candle-to-structure bridge head `948ff5fb267b62a732fbcf5b54c925215e5373cb`: exact-head run `39241690905` succeeded. It reuses the existing causal structure observer and produces a Lightweight Charts-compatible OHLC projection; it is not a frontend, HTTP server, or completed TradingView integration.
- Confirmed roadmap gate `docs/roadmap/TRADINGVIEW_COMPARABLE_CHART_DATAFEED_GATE_V1_2026-10-19.md` is already present on PR #331. Do not create another chart renderer or another adapter merely to duplicate these components.
- The official Tabdeal docs and official SDK surface reviewed in this pass still do not document a native OHLCV/kline endpoint. The recorded candidate route probes returned 404 for the tested symbol forms. This does not prove the website chart has no private datafeed; the actual chart network contract remains the next unresolved source-discovery task.
- No sequence dependency is demonstrated for ordinary OHLCV availability. Do not expand or synchronize PR #245 just to unblock candle/chart work.
- No repository runtime code, live collector, account, deployment, or trading behavior was changed by this review. No new live network probe was run in this pass.
- Status remains `HOLD / NO_TRADE_ONLY`. Native adapter bridge tests passing do not establish approved production venue, Tabdeal chart parity, rendered-chart parity, or release authorization.


## Continuation update — Sequence-independent candle path (2026-10-19)

- Re-checked PRs #320 and #329–#331 plus the TradingView/comparable chart roadmap before taking further action; existing adapters, bridge, causal structure observer, and chart-payload projection are reused rather than rebuilt.
- Updated issue #317 to split the work into independent gates: (A) Futures clock evidence, (B) native OHLCV/official-chart parity, and a separate conditional Sequence workstream.
- Explicit rule now recorded in issue #317: trade-sequence vectors are **not** prerequisites for ordinary OHLCV retrieval, candlestick rendering, or price-only causal structure observation. Sequence work only gates features that need trade-event identity, replay protection, loss detection, or ordering.
- Tabdeal chart-feed discovery remains the actual candle/chart blocker: the two tested public `/r/fapi/v1/klines` candidates returned 404 for `BTCUSDT` and `BTC_USDT`, while the official website chart's own datafeed contract has not yet been verified. These 404s rule out only those tested routes; they do not prove that no chart-specific feed exists.
- Current chart path remains an integration task, not a new market-data engine: select/verify an eligible frontend entry point, use the existing canonical candle boundary, and prefer the approved Lightweight Charts route unless the project becomes eligible for TradingView Advanced Charts licensing/access. Do not create a duplicate frontend merely to claim progress.
- The public Tabdeal chart page could not be extracted by the available web extraction service in this pass. No chart network request, collector activation, code/runtime change, deployment, or live-trading action was performed.
- Safety disposition remains `HOLD / NO_TRADE_ONLY`. Existing exact-head offline CI results remain bounded evidence; they do not establish live Tabdeal chart parity, deployment, or trading readiness.


## Master checkpoint addendum — run audit and progress baseline (2026-10-19 15:37 +03:30)

### Run audit
- Exact checkpoint commit `4db30da80aad4e2c494ac0b2b8e202f7dfc89479`: 26/26 observed PR-triggered workflow runs completed with `success`; combined commit status endpoint returned no status entries, so the run list—not the empty combined-status response—is the evidence here.
- Previous checkpoint commit `33127133880d5750c5792cc14f76b2c9a99cb75d`: 26/26 observed PR-triggered workflow runs completed with `success`.
- Native candle bridge PR #329 head `70a3949a2b512dead8b00ec57c92c91d2c103862`: 26 observed runs, all successful.
- Adapter contract PR #330 head `ec76f51dc6511603ad429e21ebea874d51238cd0`: 2 observed runs, both successful.
- Structure bridge PR #331 head `948ff5fb267b62a732fbcf5b54c925215e5373cb`: 3 observed runs, all successful. An earlier head `54a954a50f065e0f38df41a6977b48e34cab7b0e` had two failures; a later head has green runs. Do not rerun obsolete failures against the old SHA unless reproducing the regression is specifically needed.
- The Effective Evidence Audit workflow was observed as `skipped` on the current default-branch SHA `4956cf519c445edd004fdd4e763bdb3347a7ada9` in the workflow_run-triggered run. This is not a failed test; its gate condition/trigger behavior still merits inspection. No current failing run was found in the latest 100 returned Actions runs.
- Combined status API returned an empty statuses array for all five inspected SHAs. Do not interpret that as green by itself; use the exact-head Actions runs above.
- No CI workflow was rerun because current target-head runs were green and no active failing job was identified. Avoid spending runs on superseded commits.

### Last-24-hours activity window
Window: 2026-10-18 15:37 through 2026-10-19 15:37, UTC+03:30.
- Refined issue #317 into separate Futures-clock, native OHLCV/chart-parity, and conditional trade-sequence gates.
- Reviewed the chart roadmap and PRs #320, #329, #330, #331, and #245 to avoid duplicate candle engines, duplicate adapters, and unnecessary coupling of Sequence to chart display.
- Reconfirmed public Tabdeal Futures `/r/fapi/v1/time`, `exchangeInfo`, and `depth` evidence, plus 404s for only the two tested `/r/fapi/v1/klines` candidates (`BTCUSDT`, `BTC_USDT`). The website chart's actual datafeed remains unknown.
- Added and verified checkpoint documentation. PR #318 remains open/draft; documentation being committed is not equivalent to merging it into main.
- Exact-head offline CI remained green for the currently reviewed checkpoint and native-candle bridge heads; no live chart capture, production deployment, or trading activation occurred.

### Whole-project progress baseline (engineering estimate, not a GitHub-native metric)
Percentages are approximate completion estimates for the defined workstream, not a claim that all release criteria are met. Workstreams overlap, so do not sum them.
- Core architecture, existing engines, and reuse-first integration: 76%.
- Data-source identity, provenance, and raw-evidence integrity: 62%.
- Native OHLCV adapters and candle-to-feature bridge: 58%.
- Exchange clock, sequence semantics, and event-ordering safety: 43%.
- Strategy/backtest/feature validation automation: 70%.
- Chart UI / TradingView-compatible datafeed and source parity: 28%.
- Operational resilience, supervised collection, and recovery proof: 52%.
- Security, independent/legal acceptance, and release readiness: 24%.
- **Overall project estimate: 53%** (weighted planning estimate; uncertainty about ±8 percentage points because there is no frozen, fully enumerated requirements denominator).

### Highest-impact blockers / next actions
1. Discover the official Tabdeal Futures chart's actual network/datafeed contract in a browser that can inspect the chart; capture raw request/response evidence and hash it.
2. Select/verify the real HES frontend entry point. Prefer existing components; use Lightweight Charts if an eligible frontend is established. TradingView Advanced Charts requires approved access and an eligible license.
3. Verify the Futures clock offset using repeatable raw samples and an explicit tolerance.
4. Inspect why Effective Evidence Audit is skipped on default-branch workflow_run events and add a safe test for intended trigger conditions if a real defect is confirmed.
5. Keep Wallex volume-dependent features blocked until volume semantics are authoritatively reconciled.
6. Keep sequence vectors independent from ordinary OHLCV/candlestick work; sequence remains a gate only for event-ordering-dependent features.
7. Preserve `HOLD / NO_TRADE_ONLY`; no deployment, collector activation, or live trading authorized.
