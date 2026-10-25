# HES Trade Agent DNA & Roadmap — Canonical Frontend Location
Recorded: 2026-10-25
Status: candidate path verified; production deployment remains unverified.

## Canonical repository
- GitHub repository: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- Local VPS checkout: /opt/hes-trade-agent
- Repository role: HES data-foundation / market-data / trading-agent repository. It is not accurate to call the currently checked-out VPS tree a deployed production frontend.
- Candidate frontend entrypoint: `web/dashboard.py`
- Candidate chart assets: `web/static/third_party/lightweight-charts/5.0.8/`
- Candidate data/analysis contracts: `forward/native_ohlcv_v1.py`, `forward/native_ohlcv_feature_pipeline_v1.py`
- Candidate Signal Agent integration: PR #362, `GET /api/signal?symbol=BTCUSDT&interval=15m`, dashboard panel.

## Exact review chain and state
- PR #297: canonical Native OHLCV source/feature pipeline foundation.
- PR #346: dashboard using the same NativeOHLCVBatch for chart projection and descriptive features; local pinned Lightweight Charts build; read-only UI.
- PR #362: stacks Signal Agent endpoint/panel on the dashboard.
- These are Draft/open/unmerged candidates as last verified 2026-10-25. PR #361 overlaps Signal Agent files; do not merge it independently of #362. PR #340's competing dashboard implementation was closed unmerged.
- Candidate tested head for PR #362: `5b5b26e92e9d0d4c167dc5af035245e90ccaece4`.
- Reported exact-head CI: dashboard native path, browser render, Signal Agent regression, and Signal Agent contract succeeded; live WebSocket smoke was skipped because PR is Draft. CI on GitHub runners does not prove connectivity or rendered parity on the authorized VPS.

## Production acceptance blockers
1. The currently authorized VPS checkout at `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`, does not contain the candidate `web/dashboard.py` path; it is also dirty. Do not reset, clean, copy PR code over it, or merge blindly.
2. The selected Binance Spot feed has documented reachability problems from the authorized runtime; candidate PR notes record that VPS chart/feed parity is UNVERIFIED.
3. No approved production deployment/reverse-proxy mapping or authorized browser capture proves the dashboard is deployed.
4. Provider qualification remains open; no provider is approved merely because GitHub CI passed.

## Anti-rediscovery rule
Do not repeat generic repository searches. Canonical candidate location is this repository + `web/dashboard.py` in PR #346, with Signal Agent integration in PR #362. Reopen discovery only if new evidence contradicts this or new repository access/URL/deployment manifest appears. Continue work against this candidate and the existing PR dependency chain; no parallel UI.

## Roadmap
- Continue exact-head dependency/overlap review for #297 -> #346 -> #362.
- Resolve approved-runtime data-source reachability and provider qualification.
- Build/test the candidate in an isolated checkout at the exact SHA; then obtain authorized runtime browser/render evidence.
- Only after gates pass, plan controlled deployment with rollback and security checks.
- Keep live execution disabled (HOLD / NO_TRADE_ONLY).
- Delivery target: 2026-11-19.


## Canonical global market-data provider decision — 2026-10-25
- **Primary candidate source for HES market-analysis candles: Gate.io public Spot API/WebSocket**, source identity `gateio_public_spot`, symbol `BTC_USDT`. This records the project's existing migration away from Binance because Binance public endpoints returned access/reachability failures from the authorized VPS/runtime (timeouts, HTTP 451); do not restart generic Binance troubleshooting absent new evidence.
- Existing VPS collectors are already active for 15m, 1h, and 4h. Canonical files: `data/forward/global_market_candles_v1.jsonl`, `data/forward/global_market_candles_1h_v1.jsonl`, `data/forward/global_market_candles_4h_v1.jsonl`. Existing fail-closed reader: `forward/global_market_data_reader_v1.py`; schema `hes_global_candle_v1`; common input boundary remains the existing NativeOHLCV pipeline. No second candle/indicator implementation.
- Latest read-only integrity scan on 2026-10-25: 599 (15m), 524 (1h), 506 (4h) rows; all rows had unique/increasing open times, expected close boundaries, correct source/symbol/timeframe identity, closed candles, and valid OHLCV bounds; no gaps/duplicates were detected in the stored rows. Latest candle age was 923 seconds and within the current reader freshness windows (2× each timeframe).
- Four Gate.io systemd units (15m, 1h, 4h, soak) were active/enabled. Soak sample 28 of 24h soak reported ok=true at elapsed 1,622 seconds (~27 minutes). **This is not yet 24/7 qualification**. Require an uninterrupted 86,400-second soak, monitoring of reconnect/backfill/gap/stale failures, and end-of-run data-quality report before declaring production-grade 24/7 stability.
- Architecture decision: treat Gate.io as the **canonical operational source candidate for HES**, not a claim that it is a consolidated all-venue global index. Trading/chart data remain market-data-only; exchange execution adapter remains separate. Never auto-fallback to Binance or another provider; fail closed on stale/gap/source mismatch. Keep HOLD / NO_TRADE_ONLY until the 24h soak, dashboard integration, target-runtime chart/API parity, and release gates pass.


## Product acceptance revalidation — 2026-10-25 12:18 UTC
- Fresh sole-VPS check: checkout `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`, 58 dirty status entries, no `web/dashboard.py` in checkout. Preserve the worktree; no deployment or destructive Git operation.
- Existing Gate.io units (15m, 1h, 4h, soak) active. Current journal counts: 600/524/506 candles; soak sample 30 `ok=true`, elapsed 1,742 seconds (~29 minutes) out of 86,400 seconds. 24-hour qualification remains pending.
- **Important integration mismatch:** PR #362 dashboard/strategy provider still hardcodes Binance Spot source semantics, while the sole VPS operational candidate is Gate.io Spot. The candidate stack is not product-accepted until an explicit tested Gate.io adapter feeds the existing `NativeOHLCVBatch` and feature pipeline; do not solve this with string replacement or a parallel candle model.
- Exact-head PR #362 checks: dashboard/native path, browser render, Signal Agent regression and contract PASS; live WebSocket smoke SKIPPED. Hosted CI does not prove VPS reachability or target-runtime parity.
- Acceptance remains blocked on 24h soak/reconnect evidence, Gate.io adapter/volume semantics and negative tests, exact-SHA browser/API parity, authorized runtime/deployment/rollback evidence, and independent symbol-mapping/risk approvals. Keep `HOLD / NO_TRADE_ONLY`.
- Target delivery: **2026-11-19**; risk checkpoint: **2026-10-26**. Do not repeat repository discovery or re-investigate Binance absent new authoritative evidence.
