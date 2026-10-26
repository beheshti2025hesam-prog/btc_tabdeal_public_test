# HES Trade Agent — Gate.io Dashboard + Signal Agent Integration Checkpoint — 2026-10-26

## Disposition

**Integration candidate CI: PASS. Product/release: HOLD / NO_TRADE_ONLY.** Target delivery remains 2026-11-19. This checkpoint documents a draft integration; it does not authorize merge, deployment, or live execution.

## Canonical implementation path

- Existing dashboard entrypoint: `web/dashboard.py` (one UI; no parallel frontend).
- Chart/data adapter: `forward/native_ohlcv_gateio_v1.py`.
- Canonical batch contract and validation: `forward/native_ohlcv_v1.py`.
- Feature pipeline: `forward/native_ohlcv_feature_pipeline_v1.py`.
- Existing Signal Agent composition: `forward/signal_agent_v1.py`.
- Dashboard read-only routes: `GET /api/candles`, `GET /api/signal`, `GET /healthz`.
- Vendored chart library: `web/static/third_party/lightweight-charts/5.0.8/`; no external runtime chart CDN.
- Candidate PR: [#387](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/387), stacked on Gate.io dashboard candidate PR #375, browser-pixel gate PR #378, and the existing native OHLCV/dashboard ancestry. Keep Draft until all release gates pass.

## Changes in this candidate

- Reuses the same validated Gate.io batch/cache for chart and Signal Agent; venue/product/symbol/timeframe are passed into the agent scope.
- Signal panel and endpoint expose status and block reasons. Missing directional structure, strategy evidence, symbol mapping, or approved risk geometry remains blocked; no fabricated evidence or feature-quality substitution.
- Execution remains disabled. The dashboard is read-only and has no order-submit route.
- Reuses existing Signal Agent, strategy policy, opportunity/risk policies, order-block context, and disagreement-arbitration code instead of implementing parallel components.

## Exact-head CI evidence

Candidate head at checkpoint: `1d1806200a67378f1b31773d0ed5d3943f4a0c59`.

- Dashboard/native path: **48 passed, 5 subtests passed**.
- Signal Agent contract: **90 passed**.
- Signal Agent regression: **96 passed**.
- Browser render: **PASS**; 239 closed Gate.io 1m candles; chart input matches API batch; displayed close and volume match source; no external chart CDN; visible-candle pixel check found 1,019 green and 1,681 red candle-color pixels; `execution_enabled=false`.
- WebSocket live smoke: **SKIPPED**, not passed. Gate.io WebSocket parity/reconnect behavior is not certified by this CI.
- Separate VPS checkout full suite: **417 passed in 5.82s** on 2026-10-26; this is a different dirty runtime checkout, not a substitute for full-suite CI on this PR head.

## Runtime and remaining blockers

- The sole VPS checkout `/opt/hes-trade-agent` is on `feat/gateio-global-market-data-v1`, HEAD `b2466bc11821`, with 11 tracked modifications and 50 untracked paths. Do not clean/reset/checkout/overwrite it; no merge or deploy has occurred.
- The actual dashboard runtime is not installed/verified on the VPS. `nginx.service` and `docker.service` were not found; there is no registered HES dashboard service. Do not invent a second frontend or silently activate a service.
- The v2 Gate.io 24-hour soak was still running at approximately 72,182 seconds / 1,202 samples at 2026-10-26 07:51 UTC. Acceptance requires one uninterrupted run >=86,400 seconds and >=1,400 valid samples, no invalid rows/gaps, a final passing summary, final SHA-256, and independent audit. Do not combine v1 and v2 or restart the active run.
- Separate reconnect/restart/session-isolation fault injection remains required.
- Strategy-level evidence providers and independent risk approval are not wired/approved for this Gate.io scope. `NO_TRADE` is mandatory.
- The dirty VPS runtime lineage and target deployment/rollback evidence remain unresolved.

## Release schedule

- 2026-11-12: scope freeze; unresolved mandatory gates remain release-blocking.
- 2026-11-16: release candidate only after exact-SHA regression, chart/source parity, security/config audit, continuous soak, rollback, and independent review pass.
- 2026-11-19: target delivery, not a waiver of safety gates.
