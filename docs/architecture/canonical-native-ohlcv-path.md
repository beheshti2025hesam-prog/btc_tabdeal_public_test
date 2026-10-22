# Canonical Native OHLCV Path — Architecture Decision Record

**Status:** Proposed; not merged or approved for production  
**Delivery target:** 2026-11-19 (28 Aban 1405)  
**Safety state:** HOLD / NO_TRADE_ONLY  
**Scope:** Repository architecture only. No deployment, live collector, trading, or order permissions.

## Decision

Keep the rich native OHLCV contract and feature-processing path from PR #297 as the canonical internal data contract. Reuse the source-ingestion and dashboard work in PRs #345 and #346 only through that contract. Preserve the fail-closed volume gate introduced in PR #349. Do not merge any PR as part of this decision.

## Evidence reviewed

The following PR heads were used as comparison snapshots; re-check current heads and exact-head CI before any acceptance decision:

- PR #297: `1ebc0046457a05fe30a43db0addd567c88dcc79`
- PR #345: `925f822a2bceb9747621509faa534e83620d47ce`
- PR #346: `e403732af4278e394458028d023de2a69233d358`
- PR #349: `e95565844e82c8f9a1e496a2d8766931f0411b52`

Relevant files observed in those snapshots:

- PR #297: `forward/native_ohlcv_v1.py`, `forward/native_ohlcv_feature_adapter_v1.py`, `forward/native_ohlcv_feature_pipeline_v1.py`, `forward/native_ohlcv_forward_runner_v1.py`, and `forward/native_ohlcv_collector_v1.py`.
- PR #345: `forward/binance_market_data_source_v1.py`, `forward/native_candle_bridge_v1.py`, and `forward/candle_normalizer_v1.py`.
- PR #346: `forward/native_ohlcv_stream_transport_v1.py`, `forward/native_ohlcv_websocket_v1.py`, and `web/dashboard.py`.
- PR #349: changes to the native feature pipeline and dashboard, including the volume-semantics fail-closed behavior and opt-in stream startup.

The repository README describes the default-branch project as a public Tabdeal BTC/USDT futures trade-data collector and explicitly says it does not use Binance. Therefore these PR snapshots must not be described as already integrated into `main` or as a verified production application.

## Data-path comparison

| PR | Responsibility | Architectural implication |
|---|---|---|
| #297 | Rich native OHLCV batch/validation, feature adapter and pipeline, forward runner and collector | Canonical internal contract and feature path |
| #345 | Binance REST/WebSocket source plus a separate `BinanceCandle` / `NativeCandleBatch` bridge and normalizer | Useful source-ingestion capabilities, but risks a second internal candle model |
| #346 | Dashboard, historical REST path, optional WebSocket transport and chart rendering using the native OHLCV path | Reusable UI/transport work, subject to frontend identity and exact-head checks |
| #349 | Fail-closed gate when volume semantics are unapproved; stream startup opt-in by explicit environment setting | Keep as safety requirements; no automatic live stream startup |

The two bridge models are not assumed to be equivalent. Before adapting PR #345, map every field and invariant to the PR #297 contract. In particular, preserve market identity, symbol, interval, timestamps, closed-candle status, Decimal precision, raw volume and available source/provenance/gap metadata. Do not silently drop fields or infer volume meaning.

## Minimum-change implementation plan

1. **Do not add another candle contract.** Make the existing PR #297 native OHLCV batch the boundary between source adapters, feature computation, persistence and chart consumers.
2. **Adapt at the source boundary.** Keep the Binance REST/WebSocket source logic from #345 where useful, but normalize it into the canonical #297 contract. Avoid a second downstream feature pipeline or parallel bridge.
3. **Unify history and stream normalization.** REST backfill and WebSocket updates must produce the same canonical representation. On reconnect, backfill the gap and reconcile closed candles before treating the stream as continuous; deduplicate and reject stale-session events.
4. **Share the same batch.** The chart and feature pipeline must consume the same normalized batch and market identity, not separately fetched or differently normalized candles.
5. **Retain #349 safety gates.** Volume-dependent decisions remain unavailable unless volume semantics are explicitly approved. Preserve raw source volume; do not add a guessed multiplier. Stream startup remains disabled by default.
6. **Test before proposing code integration.** Add/retain contract tests for market/symbol/interval identity, Decimal precision, open versus closed candles, duplicate and stale events, REST/stream reconciliation, missing intervals, malformed volume, and default-disabled stream startup.
7. **Do not imply production readiness.** The actual frontend repository/entry point and authorized VPS #1 execution environment remain separate delivery blockers until evidenced. A CI-rendered dashboard is not proof that the actual HES frontend is integrated.

## Acceptance evidence required

- Exact PR head SHA and CI results for each proposed integration commit.
- Contract tests showing one canonical batch feeds both chart and feature pipeline.
- Reproducible chart capture tied to the same symbol, interval and UTC window as the normalized source data.
- REST/WebSocket gap recovery and stale-session isolation evidence.
- Volume semantics documented from authoritative evidence before volume-dependent decisions can be enabled.
- Actual frontend repository and entry point identified, plus authorized read-only/non-trading test access to VPS #1.
- No merge, deployment, collector activation, order placement, or trading as part of this ADR.

## Explicit non-goals

- No merge of PR #297, #345, #346, or #349.
- No frontend clone or parallel dashboard.
- No activation of live collectors or trading.
- No weakening of acceptance gates.
- No claim that Wallex volume semantics or operational reconnect isolation are resolved.


## Implementation follow-up — 2026-10-22

The existing dashboard branch was updated rather than creating a parallel WebSocket parser PR. The current branch already contained a parser built on `NativeCandle` and `normalize_native_klines`; the temporary duplicate PR #352 was closed unmerged to avoid duplicate implementation.

On `feat/native-ohlcv-dashboard-single-path-20261021`, exact head `a2f5940d28d754186293a47299d3e8335db84667`:

- The WebSocket parser now rejects non-string/invalid identities with a controlled fail-closed error, hashes the exact payload bytes, and only admits closed candles through the canonical normalizer.
- `NativeOHLCVFeaturePipelineV1` defaults `volume_semantics_approved=False`; readiness and the feature snapshot remain blocked with `VOLUME_SEMANTICS_UNAPPROVED` unless explicit approval is supplied. No approval was supplied by this change.
- Dashboard stream state reports `disabled` by default and changes to `starting` only when `HES_BINANCE_STREAM_ENABLED=1`; a regression test asserts that the default path does not start a worker thread.
- Exact-head deterministic dashboard/source/feature/WebSocket/transport/reconciliation suite: **44 passed** (workflow run [39819029660](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39819029660)).
- Exact-head browser render smoke: **passed** (workflow run [39819029616](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39819029616)). The evidence records 239 closed BTCUSDT Spot 1m candles, a 1028×362 chart canvas, chart-input/API-batch equality, displayed close and raw volume matching the same batch, no external chart CDN request, and execution disabled. UI status was `FEATURES GATED: VOLUME_SEMANTICS_UNAPPROVED · stream disabled`.
- Live WebSocket smoke was **skipped** because the PR remains Draft. This CI render is not proof of integration into the actual HES frontend or connectivity on authorized VPS #1.

This is branch-level verification only: no PR merged, no production deployment, no live collector or WebSocket started, and no order/trading path enabled. Overall status remains `HOLD / NO_TRADE_ONLY`.


## Parser envelope hardening — 2026-10-22

A further negative case was added after review: wrapped WebSocket messages must have a `stream` envelope consistent with the event's own symbol and interval. This prevents accepting a valid-looking `data` object under a contradictory stream label. The existing parser still checks the caller-requested symbol/interval separately, and only closed candles enter the canonical normalizer.

- Exact dashboard branch head: `2657879f1ce4c632c5f94e2e93b4117468411e16`.
- Exact-head deterministic suite: **44 passed** — [run 39822079791](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39822079791).
- Exact-head browser render smoke: **PASS** — [run 39822080587](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39822080587). It rendered 239 closed BTCUSDT Spot 1m candles into a 1028×362 canvas; chart input matched the API batch, displayed close and volume matched source values, no external chart CDN was requested, and execution stayed disabled. UI reported `FEATURES GATED: VOLUME_SEMANTICS_UNAPPROVED · stream disabled`.
- Live WebSocket smoke remained **skipped**, not passed.

The separate safety-only PR #349 was closed unmerged as superseded because its fail-closed volume gate, default-disabled stream behavior and regression coverage are now included in the #346 branch. PR #346 remains Draft. No deployment or production activation occurred.

## References

- [PR #297](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/297)
- [PR #345](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/345)
- [PR #346](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/346)
- [PR #349](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/349)
- [Roadmap issue #334](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/issues/334)
