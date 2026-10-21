# Binance single-source integration checkpoint — 2026-10-21

## Status
**HOLD / NO_TRADE_ONLY — integration is not production-complete.**

This checkpoint records the actual state after inspecting the HES repository and VPS and capturing a fixed-window native candle comparison. It deliberately distinguishes adapter/contract readiness from live application wiring.

## Reuse-first findings
- Existing source adapter: `forward/binance_market_data_source_v1.py` on PR #345 branch `feat/binance-single-market-data-path-20261021`.
- Existing canonical normalizer: `forward/native_candle_bridge_v1.py` on the parent integration branch. The Binance adapter already exposes `fetch_canonical_batch()` and `closed_event_to_canonical_batch()`; do not create another candle engine.
- Existing chart projection: `to_lightweight_chart_payload()` on the native candle bridge branch. It is a payload projection, not a frontend, HTTP endpoint, or deployed consumer.
- The connected GitHub installation exposes only `beheshti2025hesam-prog/btc_tabdeal_public_test`; recursive inspection of the repo and VPS found no verified HES frontend package, chart entry point, or UI consumer. Do not create a parallel frontend to mask this missing dependency.
- The VPS `/opt/hes-trade-agent` has no active HES runtime service. `hes-trade-agent-collector.service` reports failed and `hes-forward-tabdeal-collector.service` is inactive.
- Direct VPS HTTPS access to Binance timed out; this host cannot currently perform the required live REST/WebSocket smoke. No service was enabled or restarted.

## Fixed-window API comparison
Evidence: `evidence/binance_spot_btcusdt_klines_uiklines_fixed_window_2026-10-21.json`

- Profile: `binance / spot / BTCUSDT / 1m`, UTC.
- Compared Binance Spot `/api/v3/klines` and `/api/v3/uiKlines` for the exact window `1792593780000..1792594079999`.
- Five common candle open times were compared across open time, OHLC, base/quote volume, close time, trade count, taker-buy base/quote volume, and the final ignore field.
- Result: **0 field mismatches across the 5 common candles**.
- Limitation: these are structured connector results, not raw HTTP transport captures. This is API-to-API parity, not rendered-chart parity and not evidence of the HES frontend consuming the data.

## Integration gates still open
1. Obtain/locate the authorized existing frontend repository and entry point; no verified path was found in currently connected sources.
2. Restore authorized outbound HTTPS for the target runtime or provide an approved runtime where Binance public REST/WebSocket access is available.
3. Wire the existing Binance adapter and canonical bridge to the actual read-only analysis consumer, with durable candle identity/idempotency, REST reconciliation on reconnect, stale-feed fail-closed behavior, gap reporting, and source/timeframe/quality lineage.
4. Run live end-to-end evidence on the target runtime and capture same-window source-to-render comparison in the actual chart. API-to-API equality does not satisfy this gate.
5. Run exact-head tests for any code change and record the tested commit and run.

## Safety
- Spot and USDⓈ-M Futures remain separate market identities; never mix their candle histories.
- Read-only market-data access only; no account credentials or order APIs.
- No collector activation, deployment, merge, evidence-registry promotion, or trading authorization is implied.
- Keep `HOLD / NO_TRADE_ONLY` until runtime wiring and rendered parity are evidenced.
