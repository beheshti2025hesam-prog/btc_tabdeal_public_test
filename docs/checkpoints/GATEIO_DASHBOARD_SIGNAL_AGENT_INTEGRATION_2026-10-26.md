# HES Trade Agent — Persisted Gate.io Feed + Signal Agent Integration Candidate
**Date:** 2026-10-26 (UTC)

## Disposition

**Application-code head `955a747f21a335b83f2c78799c81f9117adfac68`: exact-head full-suite and browser CI PASS.** The documentation checkpoint is being refreshed after those results; the documentation-only update does not change application code. Product/release remains **HOLD / NO_TRADE_ONLY**. Target delivery remains 2026-11-19. This draft does not authorize merge, deployment, service activation, or live execution.

## Canonical data path

- Existing dashboard entrypoint: `web/dashboard.py`; no parallel UI.
- Public feed writer: `forward/global_market_data_gateio_v1.py`, running as read-only 15m/1h/4h systemd feeds.
- Canonical persisted reader: `forward/global_market_data_reader_v1.py`; both chart and Signal Agent route use it through the same validated `NativeOHLCVBatch`/cache path.
- Routes: `GET /api/candles`, `GET /api/signal`, and `GET /healthz`.
- Both API responses expose `source=gateio_public_spot`, `source_reader=global_market_data_reader_v1`, and the same `input_batch_sha256`.
- Browser must not make direct exchange REST requests; the chart library is locally vendored.
- Supported chart scope: Gate.io Spot / BTCUSDT / persisted closed candles at 15m, 1h, and 4h. Signal evaluation is limited to 15m.

## Implementation lineage

- Combined draft PR: [#388](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388), based on persisted-feed dashboard PR #383.
- Base commit: `bf6627571802f2d1aaac930dc22fb6437b11ac04`.
- Signal Agent source candidate: PR #387 head `f82fa23017cd7e705fe5e208d7f8a5e6e6a102f6`.
- The combined candidate preserves PR #383's persisted reader path while adding the Signal Agent route and contract tests. Do not merge PR #383 and #387 independently; review ancestry/overlap before any merge.

## Exact-head CI evidence — application code head `955a747f21a335b83f2c78799c81f9117adfac68`

- Full repository regression: **599 passed, 5 subtests passed** — run [40317136628](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136628).
- Dashboard single-path: **PASS** — run [40317136487](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136487).
- Browser render/pixel test: **PASS** — run [40317136520](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136520); artifact SHA-256 `15c62ebe7a486ca6fd5c5c5e70c04ddd500c033802239ee7f59973d4628e826b`.
- Browser evidence: 239 closed candles; canvas 1012×362; visible candle-color pixels 1,709 green / 1,239 red; no external chart CDN or direct exchange REST request from the browser; displayed close and volume match the source.
- **Same-batch proof:** chart and Signal Agent `input_batch_sha256` both equal `40fa0e34fe6cdde3c0bce92c48c9768428a3288bf6611aa1fbc16c9d72e08332`. Signal status is `BLOCKED`, decision is `NO_TRADE`, and execution is disabled.
- Native OHLCV WebSocket live smoke: **SKIPPED**, not passed.
- Local isolated combined-tree suite: **599 passed, 5 subtests passed**; Python compile and Node syntax checks passed.

## VPS soak and restart evidence

- The uninterrupted v2 Gate.io soak completed with `duration_seconds=86400`, `samples=1439`, `max_sample_gap_seconds=60.742`, `wall_duration_seconds=86400.094`, `errors=[]`, and independent audit status **PASS**.
- Soak log SHA-256: `df499e17f6366e69ab14ab17adc2ed7e2ac9e205e4d1b1925bbd6284de975c44`.
- Independent audit report: `/srv/hes-evidence/gateio/gateio_feed_soak_audit_20261026.json`; report SHA-256 `ecc9dff5780edfb8d25e32bab698a27f362dc16b7dedbc549430f4990bfdc8bd`. Auditor SHA-256: `dff1f76e86ebdb5dbc9eda6f648bfc7a6f8b4094ee470f761e236cea8e9f9446`.
- Controlled post-soak restart test **PASS**: `hes-global-market-data-gateio.service` PID changed from `237849` to `273642`; service returned active; `HES_GLOBAL_MARKET_START` and `HES_GLOBAL_MARKET_WS_SUBSCRIBED` were observed; the canonical reader validated all three timeframes after restart with no duplicate or non-monotonic candle timestamps.
- Restart evidence: `/srv/hes-evidence/gateio/gateio_feed_restart_fault_test_20261026.json`; SHA-256 `426620bc806b2ead26843e0e361ca1b658468b3e2d69d3cf67cd16da65968d0f`.
- A separate mocked disconnect/reconnect harness passed: two connection attempts, REST reconciliation called twice, successful subscription observed, reconnect logged. This is not a live network fault-injection result.
- After restart, the one-shot analysis runner consumed the latest closed 15m candle at 2026-10-26 11:45 UTC and returned `NO_TRADE`; `execution_enabled=false`, `orders_placed=false`.

## Sole VPS state and remaining blockers

- Live checkout `/opt/hes-trade-agent` remains on HEAD `b2466bc118217dcc6446498effe38181589ed2db` with a dirty worktree. Do not reset, clean, checkout, or overwrite it.
- Active feed services: 15m, 1h, and 4h. The completed soak service is inactive as expected.
- The actual dashboard is **not installed or verified as a service on the VPS**. No dashboard deployment or service activation was performed.
- Strategy-level structure/confirmation providers, independent risk approval, and executable venue symbol/instrument mapping remain unapproved. `NO_TRADE` is mandatory.
- Open PRs remain Draft/HOLD without submitted reviews. CI success is not production deployment or trading approval.

## Release control

Keep PR #388 Draft/HOLD until the documentation-only checkpoint update's CI completes, the real frontend runtime/deployment and rollback path are verified, risk/mapping evidence is approved independently, and the final non-duplicated PR ancestry receives review. No live trading or deployment is authorized by this checkpoint.
