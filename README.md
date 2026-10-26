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
- Gate.io Spot candle source: `forward/native_ohlcv_gateio_v1.py`.
- Canonical candle/batch validation: `forward/native_ohlcv_v1.py`.
- Feature pipeline: `forward/native_ohlcv_feature_pipeline_v1.py`.
- Signal Agent composition and policy gates: `forward/signal_agent_v1.py`, `forward/strategy_policy_v1.py`, and the existing confirmation/risk/decision modules.
- Locally vendored TradingView Lightweight Charts 5.0.8: `web/static/third_party/lightweight-charts/5.0.8/`.

Read-only endpoints are `GET /api/candles`, `GET /api/signal`, and `GET /healthz`. Chart and signal analysis reuse the same validated batch. If freshness, integrity, evidence, scope, strategy, or risk gates fail, the system fails closed. No order-submit route is provided and execution remains disabled.

**Market-data semantics:** Gate.io Spot is the selected single-venue reference source for this candidate. It is not a consolidated multi-exchange feed. The exchange execution adapter is a separate concern and is not implied to be connected by this dashboard.

## Current integration candidate

- Draft PR: [#387 — connect existing Signal Agent to canonical Gate.io dashboard](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/387).
- Base Gate.io dashboard candidate: [PR #375](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/375).
- Visible candlestick pixel gate: [PR #378](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/378).
- Native OHLCV foundation and dashboard ancestry must be reconciled by exact commit/patch review before any merge. These PRs are candidates, not accepted production changes.

## Data foundation / historical component

This repository also contains the first Tabdeal BTC/USDT futures public trade-data collector used in the Data Foundation phase. That historical collector does not require a Tabdeal API key, access account balances, submit orders, or trade. It is not the canonical chart/analysis source for the Gate.io dashboard candidate.

## Required release gates

- One uninterrupted Gate.io soak of at least 86,400 seconds and 1,400 valid samples, a passing final summary, final SHA-256, and independent audit.
- Separate reconnect/restart/session-isolation fault injection.
- Exact-head tests and browser evidence proving chart input, displayed close, and volume match the same canonical API batch.
- Strategy-level structure/confirmation evidence, symbol mapping, and independent risk approval. Missing evidence means `NO_TRADE`.
- Verification of the actual frontend runtime, service/route, security configuration, and rollback on the sole VPS before deployment.
- Exact-SHA ancestry, regression, provenance, and independent review before release.

See [Gate.io Dashboard + Signal Agent Integration Checkpoint — 2026-10-26](docs/checkpoints/GATEIO_DASHBOARD_SIGNAL_AGENT_INTEGRATION_2026-10-26.md) for the current evidence and open gates.

## Language and attribution

- Default application language: English.
- Localization architecture supports English (`en`) and Persian (`fa`), including LTR/RTL presentation where applicable.
- Charts use TradingView Lightweight Charts™ under the vendored upstream license and NOTICE.
