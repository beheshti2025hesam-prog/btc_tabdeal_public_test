# HES Trade Agent

**Owner:** Seyed Hesameddin Beheshti Shirazi

## Product status

- Delivery target: **19 November 2026**.
- Release posture: **HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY** until all source, strategy, risk, soak, runtime, and release gates pass.
- One VPS only. Preserve its dirty checkout; no bulk cleanup, reset, or overwrite.
- Existing implementations are the source of truth: extend them; do not create a parallel dashboard, candle schema, feature pipeline, or execution adapter.

## Canonical read-only dashboard path

The current Gate.io dashboard integration candidate reuses these existing components:

- Dashboard entrypoint: `web/dashboard.py`.
- Gate.io public candle collector: `forward/global_market_data_gateio_v1.py`.
- Canonical persisted source and fail-closed reader: `forward/global_market_data_reader_v1.py`.
- Canonical candle/batch validation: `forward/native_ohlcv_v1.py`; the dashboard converts the same persisted rows into this batch contract.
- Feature pipeline: `forward/native_ohlcv_feature_pipeline_v1.py`.
- Signal Agent composition and policy gates: `forward/signal_agent_v1.py`, `forward/strategy_policy_v1.py`, and the existing confirmation/risk/decision modules.
- Locally vendored TradingView Lightweight Charts 5.0.8: `web/static/third_party/lightweight-charts/5.0.8/`.

Read-only endpoints are `GET /api/candles`, `GET /api/signal`, and `GET /healthz`. The chart and Signal Agent both read the same persisted global-feed rows through `global_market_data_reader_v1`; the `/api/candles` and `/api/signal` responses expose the same `input_batch_sha256`, and the browser smoke asserts hash equality and zero direct exchange requests from the browser. If freshness, integrity, evidence, scope, strategy, or risk gates fail, the system fails closed. No order-submit route is provided and execution remains disabled.

**Market-data semantics:** Gate.io Spot is the selected single-venue reference source for this candidate. It is not a consolidated multi-exchange feed. The exchange execution adapter is a separate concern and is not implied to be connected by this dashboard.

## Current integration candidate

- Combined persisted-feed + Signal Agent candidate: [Draft PR #388](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388), based on the persisted-feed chart path in [PR #383](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/383).
- Signal Agent source candidate: [PR #387](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/387); do not merge it independently with PR #383 because the combined candidate reuses the canonical persisted feed.
- Base Gate.io dashboard candidate: [PR #375](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/375); visible candlestick pixel gate: [PR #378](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/378).
- PR #388 exact-head full-suite and browser CI passed (599 tests + 5 subtests; browser confirms chart/signal batch-hash equality). Keep Draft/HOLD until independent review and production runtime gates pass; no merge/deployment is authorized.

## Data foundation / historical component

This repository also contains the first Tabdeal BTC/USDT futures public trade-data collector used in the Data Foundation phase. That historical collector does not require a Tabdeal API key, access account balances, submit orders, or trade. It is not the canonical chart/analysis source for the Gate.io dashboard candidate.

## Required release gates

- **Completed 2026-10-26:** uninterrupted Gate.io soak passed (86,400 seconds, 1,439 valid samples, max gap 60.742 seconds); independent audit and final SHA-256 are recorded under `/srv/hes-evidence/gateio/`.
- **Completed 2026-10-26:** controlled 15m feed restart/recovery passed; a mocked disconnect/reconnect harness passed. Live WebSocket smoke remains SKIPPED, not passed.
- **Passed on PR #388 exact head:** full-suite regression and browser render; browser evidence proves chart input, displayed close/volume, and Signal Agent consume the same canonical input-batch SHA-256.
- Strategy-level structure/confirmation evidence, symbol mapping, and independent risk approval. Missing evidence means `NO_TRADE`.
- Verification of the actual frontend runtime, service/route, security configuration, and rollback on the sole VPS before deployment.
- Exact-SHA ancestry, regression, provenance, and independent review before release.

See [Gate.io Dashboard + Signal Agent Integration Checkpoint — 2026-10-26](docs/checkpoints/GATEIO_DASHBOARD_SIGNAL_AGENT_INTEGRATION_2026-10-26.md) for the current evidence and open gates.

## Language and attribution

- Default application language: English.
- Localization architecture supports English (`en`) and Persian (`fa`), including LTR/RTL presentation where applicable.
- Charts use TradingView Lightweight Charts™ under the vendored upstream license and NOTICE.
