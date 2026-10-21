# Binance single-source integration checkpoint — 2026-10-21

## Status
**HOLD / NO_TRADE_ONLY — live application integration is not production-complete.**

This checkpoint separates source code and test readiness from an operational chart/analysis path.

## Reuse-first repository findings
- **A prior native OHLCV source and analysis consumer already exist** on draft PR [#297](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/297), branch `feat/native-ohlcv-candle-sources-20261017`: `forward/native_ohlcv_v1.py`, `forward/native_ohlcv_feature_pipeline_v1.py`, and `forward/native_ohlcv_forward_runner_v1.py`. This source already supports public Binance Spot uiKlines/klines and USDⓈ-M Futures klines, preserves raw-response SHA-256, validates closed candles/gaps, computes features, and writes a one-shot immutable observation record when explicitly enabled.
- Draft PR [#345](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/345) adds a second Binance REST/WebSocket source module, `forward/binance_market_data_source_v1.py`, and a helper path into the native candle bridge. It has useful WebSocket/reconnect contracts, but its REST source overlaps with the older native source. **Do not merge both as separate competing candle engines.** The implementation must reconcile the WebSocket transport with the already-existing `NativeOHLCVSource` contract and runner, preserving one canonical source/feature/journal path.
- Draft PR [#331](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/331) contains `forward/native_candle_bridge_v1.py` and `to_lightweight_chart_payload()`. The latter is a projection helper only—not a frontend, HTTP endpoint, or deployed consumer.
- The connected GitHub installation exposes only `beheshti2025hesam-prog/btc_tabdeal_public_test`; recursive inspection of the repository and VPS found no verified HES frontend package, chart entry point, or UI consumer. Do not create a parallel frontend to mask this missing dependency.
- The VPS `/opt/hes-trade-agent` has no active HES runtime service. `hes-trade-agent-collector.service` is failed (since 2026-10-06); `hes-forward-tabdeal-collector.service` is inactive. Both units are disabled.
- Direct VPS HTTPS access to Binance timed out. The target host cannot currently perform the required live REST/WebSocket smoke. No service was enabled, restarted, or deployed.

## Fixed-window API comparison
Evidence: `evidence/binance_spot_btcusdt_klines_uiklines_fixed_window_2026-10-21.json`

- Profile: `binance / spot / BTCUSDT / 1m`, UTC.
- Compared Binance Spot `/api/v3/klines` and `/api/v3/uiKlines` for the exact window `1792593780000..1792594079999`.
- Five common candle open times were compared across open time, OHLC, base/quote volume, close time, trade count, taker-buy base/quote volume, and the final ignore field.
- Result: **0 field mismatches across the 5 common candles**.
- Limitation: these are structured connector results, not raw HTTP transport captures. This is API-to-API parity, not rendered-chart parity and not evidence of the HES frontend consuming the data.

## Integration gates still open
1. Locate and obtain access to the authorized existing frontend repository and entry point; no verified path was found in currently connected sources.
2. Reconcile PR #345's WebSocket event stream with the existing native source/runner from PR #297; avoid duplicate REST adapters, feature pipelines, candle engines, and journals.
3. Establish durable idempotency across process restart, REST history reconciliation after reconnect, explicit gap reporting, stale-feed fail-closed behavior, and source/timeframe/quality lineage.
4. Restore authorized outbound HTTPS for the target runtime or provide an approved runtime where Binance public REST/WebSocket access is available.
5. Run live end-to-end evidence on the target runtime and capture same-window source-to-render comparison in the actual chart. API-to-API equality does not satisfy this gate.
6. Run exact-head tests for each code change and record the tested commit and run.

## Safety
- Spot and USDⓈ-M Futures remain separate market identities; never mix their candle histories.
- Read-only market-data access only; no account credentials or order APIs.
- No collector activation, deployment, merge, evidence-registry promotion, or trading authorization is implied.
- Keep `HOLD / NO_TRADE_ONLY` until runtime wiring and rendered parity are evidenced.
