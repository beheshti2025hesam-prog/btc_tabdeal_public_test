# Master Checkpoint — Canonical Frontend Candidate Location — 2026-10-25

## Durable answer
**Known candidate frontend location:** repository `beheshti2025hesam-prog/btc_tabdeal_public_test`, file `web/dashboard.py` on Draft PR #346. Signal Agent endpoint/panel integration is stacked in Draft PR #362.

Repository URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test

Candidate chart asset: `web/static/third_party/lightweight-charts/5.0.8/`.
Candidate core data path: `forward/native_ohlcv_v1.py` and `forward/native_ohlcv_feature_pipeline_v1.py`.

## Do not confuse candidate with production
- PR #297 -> #346 -> #362 is the intended review/dependency chain; all were open/draft/unmerged as last verified.
- PR #361 overlaps Signal Agent code and must not be independently merged with #362.
- Exact candidate head checked for PR #362: `5b5b26e92e9d0d4c167dc5af035245e90ccaece4`.
- Candidate GitHub CI checks passed for dashboard native path, browser render, Signal Agent regression, and contract. Live WebSocket smoke was skipped. CI is not production deployment evidence.
- Sole VPS checkout is `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, observed HEAD `b2466bc118217dcc6446498effe38181589ed2db`, dirty. It does not currently include the candidate `web/dashboard.py`. Preserve the dirty worktree; no reset/clean/merge or overwrite.
- Actual production deployment, approved runtime feed reachability, and target-runtime rendered chart/API parity remain UNVERIFIED/BLOCKED.

## Anti-duplication rule
Stop generic repo rediscovery. Treat the above as canonical candidate path. Reopen discovery only if new authoritative evidence arrives (new GitHub access, user-provided URL, deployment manifest, or newly found checkout). Do not create a parallel frontend.

## Release gates
1. Review and test dependency chain at exact current heads.
2. Resolve provider qualification and authorized runtime connectivity.
3. Isolated exact-SHA build and test.
4. Authorized browser evidence of chart/API parity on target runtime.
5. Controlled deployment plan with rollback/security validation.
Until all gates pass: HOLD / NO_TRADE_ONLY; no live execution.

Delivery target remains 2026-11-19.
DNA/Roadmap record: `docs/HES_DNA_AND_ROADMAP.md`.


## Revalidation pass — 2026-10-25 (current state)

### Exact PR dependency alignment
- PR #297 is open Draft, head `1ebc0046457a05fe30a43db0addd567c88dcc79d`.
- PR #346 is open Draft, head `5bcc4be0e098e843d7cab622489f6a7f3cc99816`; its base SHA is exactly PR #297's head SHA.
- PR #362 is open Draft, head `5b5b26e92e9d0d4c167dc5af035245e90ccaece4`; its base SHA is exactly PR #346's head SHA.
- Therefore the intended stack is currently aligned by exact parent SHAs: **#297 → #346 → #362**. This is review alignment only; none is merged or production-approved.
- PR #361 remains open Draft and overlaps the Signal Agent core; do not merge it independently of #362. PR #345 and #349 are closed unmerged. PR #340 was previously closed unmerged.
- Current workflows fetched for PR #362 head: dashboard/native source PASS; browser render PASS; Signal Agent regression PASS; Signal Agent contract PASS; live WebSocket smoke SKIPPED (not a pass). Exact run IDs: 40095520769, 40095520745, 40095520775, 40095520824, and skipped 40095520812.

### Sole VPS revalidation
- Host: `vps-second-261930`; project checkout remains `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`.
- `git status --short` count: 58 entries. `web/dashboard.py` is absent in this checkout. No reset, clean, merge, copy-over, or deployment was performed.
- The four existing `hes-global-market-data-gateio*` systemd units (main, 1h, 4h, soak) currently report active and enabled. Journal access to the soak unit was denied for the SentinelX agent identity, so current soak duration/completion is **not verified**.
- Fresh read-only connectivity probe: `api.binance.com` timed out and resolved to private address `10.10.34.34`; `fapi.binance.com` timed out; `data-api.binance.vision` returned HTTP 451. These results do not support target-VPS feed reachability.
- A nonempty `COINAPI_API_KEY` assignment was detected without printing its value. Reading file metadata was denied, and earlier PR evidence recorded an HTTP 401 from CoinAPI. Key validity/account access remains unverified; do not expose or print the key.

### Disposition
The candidate location and PR ancestry are now resolved and persisted; do not repeat generic frontend/repository discovery. **The broader frontend section is not complete for production** because the target runtime lacks verified source connectivity, target-runtime chart/API parity is absent, the candidate code is not in the VPS checkout, and the dirty checkout must be preserved. Do not merge, deploy, activate live feed/collection, or enable execution as a workaround. Continue with authorized provider/runtime access and exact-SHA acceptance evidence. Status remains **HOLD / NO_TRADE_ONLY**. Delivery target: **2026-11-19**; risk checkpoint: **2026-10-26**.


### Existing VPS feed found during the same pass
- The sole VPS already has an active Gate.io public Spot candle collector writing the same three intervals: 15m, 1h, 4h, with local files `data/forward/global_market_candles_v1.jsonl`, `global_market_candles_1h_v1.jsonl`, and `global_market_candles_4h_v1.jsonl`. Its reader is `forward/global_market_data_reader_v1.py` and normalized schema is `hes_global_candle_v1`.
- At the last read-only check (2026-10-25 around 12:08 UTC), all three collector services were active; 15m had 599 rows, 1h 524, 4h 506. The 24h soak service was active since 11:48:04 UTC; sample 21 at 12:08:06 UTC reported `ok=true`, elapsed 1201 seconds (~20 minutes), with latest candle age 486 seconds. **This is not a completed 24-hour soak.** Current soak completion remains due no earlier than approximately 2026-10-26 11:48 UTC if it runs uninterrupted.
- Direct public API probes from this VPS: Binance api.binance.com and api1/api2/api3 timed out; data-api.binance.vision returned 451; fapi.binance.com timed out. Bybit returned 403 explicitly stating access blocked from the server's country; OKX/Kraken connections timed out; Coinbase API timed out. These are read-only probes and no proxy was used.
- Gate.io is a technically reachable candidate source already feeding the VPS, but this does **not** automatically approve replacing the requested Binance profile or prove parity with a global consolidated chart. Do not silently switch the candidate dashboard from Binance to Gate.io. Any such change must reuse the existing `NativeOHLCVBatch`/feature pipeline (no second candle model), have exact-SHA tests and source identity gates, and preserve execution disabled.
