# TradingView / equivalent chart integration roadmap — 2026-10-19

## Decision

Charting integration is a high-priority HES roadmap item. Reuse the native candle bridge and existing chart/data sources; do not create a parallel candle engine, infer missing market data, or add a frontend merely to claim completion.

Current status: **PLANNED — NOT INTEGRATED**. The repository's current main branch has no verified in-repo chart frontend/widget or package manifest for a web UI. The native bridge is proposed in PR #329; real-adapter contract coverage is in PR #330. Neither PR is merged or production-wired.

## Reuse-first options

1. **Immediate analysis and parity reference:** use the exchange's existing chart page where it represents the exact venue/product/symbol. Wallex's official UDF history path has already been traced to its chart getBars source. Prior same-window samples matched OHLC for 1m and 1h, but UDF volume was exactly 2x public trade-quantity sums in 99 closed 1m bars across five symbols. Do not halve or otherwise normalize that volume without authoritative semantics. Hide/label volume-derived conclusions as unverified for Wallex.
2. **TradingView Advanced Charts:** preferred only if HES can lawfully obtain and use the library. It is not assumed to be freely available, and it does not provide market data. Implement its documented Datafeed API against HES's existing normalized candles; do not couple the chart directly to exchange endpoints.
3. **Equivalent in-product chart:** if Advanced Charts access is unavailable, evaluate TradingView Lightweight Charts or another maintained chart component only after confirming license, browser/app architecture, and owner value. This is an alternative rendering layer, not a reason to build a second data engine.

## Target data path

native venue adapter -> normalize_native_candles -> explicit chart-bar mapper -> chart datafeed

The chart mapper must remain a thin presentation boundary. It must not fetch from exchanges itself, alter raw evidence, fabricate candles, fill gaps, or promote uncertain volume semantics.

### Datafeed contract (TradingView Advanced Charts)

- onReady: advertise only resolutions actually supported by the chosen, verified source.
- searchSymbols / resolveSymbol: require explicit venue + market + canonical symbol identity; do not alias Binance BTCUSDT to Tabdeal BTC_USDT Futures.
- getBars: return only closed, validated bars; convert normalized UTC candle open times to the documented millisecond time field; preserve OHLC and the chosen volume policy; report no-data/gaps rather than synthesizing bars.
- subscribeBars / unsubscribeBars: not enabled until a verified real-time feed and session/reconnect isolation exist. Do not simulate live bars from polling or historical responses.
- Keep chart callbacks asynchronous per TradingView's documented API. Keep charting data read-only; chart integration must not expose broker/order actions.

## Source-specific safeguards

- **Wallex:** the 2x volume discrepancy is unresolved. Price/OHLC charting may proceed only with source identity visible; volume-based indicators, signals, and comparisons remain blocked or explicitly marked unverified. Daily 1D remains deferred pending timezone/boundary verification.
- **Binance:** Spot and USDⓈ-M Futures are distinct identities. A Binance chart is not evidence of Tabdeal Futures parity.
- **Tabdeal Futures:** official docs confirm the FAPI family and document public `/r/fapi/v1/time`, `/r/fapi/v1/exchangeInfo`, and `/r/fapi/v1/depth`; however, the published docs search did not identify a kline/candle endpoint. A direct live endpoint read was not verifiable through the current web retrieval path. Therefore the exact native OHLCV endpoint/schema and clock-offset evidence remain unverified—do not infer `/klines` solely from Binance compatibility. Do not substitute Binance silently; capture the exact endpoint, parameters, raw response bytes, retrieval timestamps, headers/status, and SHA-256 before claiming parity. Official docs: https://docs.tabdeal.org/ (FAPI section).
- **All sources:** retain raw response evidence and retrieval timestamps; no collector activation, evidence-registry pin, deployment, or live orders as part of chart work.

## Acceptance gates

1. Identify the actual HES runtime/UI architecture and confirm library licensing/access before choosing a rendering component.
2. Define an explicit ChartBar contract and test UTC seconds-to-milliseconds conversion, timeframe mapping, no-data, duplicate/out-of-order rejection, gaps, open-candle exclusion, symbol/market isolation, and volume policy.
3. Add offline contract tests using the pinned real adapter outputs and the existing bridge; no live network is required for unit tests.
4. Compare chart-visible OHLC against the exact venue's official chart for the same symbol, market, timeframe, and closed-bar window. Capture a rendered screenshot and its timestamp alongside raw API evidence. API-to-API agreement alone is not rendered-chart parity.
5. Enable real-time subscriptions only after transport/session/reconnect tests pass and source clocks meet a predeclared tolerance.
6. Keep the system at HOLD / NO-TRADE until the independent safety/evidence gates already defined by the project are satisfied. This document does not authorize merge, production wiring, collection, or trading.

## Official documentation consulted

- TradingView Connecting Data: https://www.tradingview.com/charting-library-docs/latest/connecting_data/
- TradingView Datafeed API: https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/
- Required Datafeed methods: https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/required-methods/

TradingView documents that Advanced Charts is a client-side charting library, requires the integrator to supply market data, and offers either a UDF adapter or a custom Datafeed API. Its documented bar time is milliseconds; other time fields commonly use seconds. Confirm the current licensing/access terms before implementation.

## Ownership and current disposition

This is a pair-owned project (user + ChatGPT); no third-party reviewer is a project prerequisite. Pair audit and exact-head CI remain the verification path. Current disposition: HOLD / NO-TRADE.
