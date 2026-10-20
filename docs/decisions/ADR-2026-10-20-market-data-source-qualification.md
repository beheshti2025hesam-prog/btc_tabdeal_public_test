# Market-data source qualification — 2026-10-20

## Status

**BLOCKED — no provider is currently approved as the common chart and analysis source.** The Yahoo Finance adapter is only a provisional, read-only USD reference for chart plumbing. It is not a certified global aggregate or trusted strategy input. No source is promoted by this decision.

## Evidence-based findings

1. **TradingView is a charting/datafeed interface, not a turnkey market-data API for this integration.** Its Advanced Charts documentation states that the library contains no market data and requires a data source or third-party provider. The Datafeed API is a bridge the application must implement:
   - https://www.tradingview.com/charting-library-docs/latest/connecting_data/
   - https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/
2. **TradingView hosted widgets are not a substitute for a programmatic strategy feed.** Its widget FAQ says widgets do not provide an API for exporting data or indicator values: https://www.tradingview.com/widget-docs/faq/data/
3. **Yahoo Finance public chart data remains unqualified.** The endpoint is unofficial; underlying venue composition, global aggregation methodology, volume definition, contractual SLA, and data-use rights are unverified. The adapter preserves volume unchanged, but preservation is not proof of semantic correctness. The recorded live smoke returned source volume `0`; volume-derived features remain disabled.
4. **CoinDesk Data API has a technical OHLCV surface, but access and legal suitability are not established.**
   - The current pricing page describes Personal as non-commercial, aggregate REST, with minute history limited to the latest hour; Start-Up as contact-priced commercial/internal-only with REST/WebSocket and minute history limited to 24 hours; Enterprise as negotiated access with broader datasets/history and bespoke terms: https://developers.coindesk.com/pricing/
   - The current API licence says access is limited to data selected under an active subscription, generally for internal use; it restricts display and use to develop/distribute products absent special written permission. It also says API data is not intended for trading purposes. Therefore none of the public tier summaries alone establishes permission to use the data as HES chart + decision input or in a trading-related product. A provider-approved written licence/use determination is a prerequisite, not a paperwork follow-up.
   - CoinDesk announced retirement of its free API tier effective **2026-05-21**; accounts without an API subscription no longer have API access: https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access
   - The Data API introduction recommends registering and supplying an API key and documents that endpoints may return 401 when a valid key is required: https://developers.coindesk.com/documentation/data-api/introduction
   - The Spot historical-minute endpoint is for a selected exchange and includes base/quote volumes; it is not automatically a cross-market aggregate: https://developers.coindesk.com/documentation/data-api/spot_v1_historical_minutes
   - The index/reference-rate historical-minute endpoint is a separate surface. Its index price and any volume-like fields must not be assumed equivalent to traded market volume: https://developers.coindesk.com/documentation/data-api/index_cc_v1_historical_minutes
   - CCCAGG methodology reference: https://www.cryptocompare.com/media/37072230/cccagg_methodology-2020-07.pdf. This older methodology document must be reconciled with the current product, instrument mapping, and licence before use.
   - No HES-owned API credential, active subscription/permission evidence, provider-approved trading-related use permission, successful authenticated raw response, or representative BTC/ETH/SOL payload is present in this repository/PR. Therefore real access and rights are **UNVERIFIED**. Do not invent or simulate live provider responses.
5. **No alternative is automatically accepted merely because it has a public endpoint.** A venue-specific endpoint (for example, one exchange's candles) is not a global aggregate. It may be used only as a clearly labelled comparison source, not silently substituted for the project's approved common source. The approved exchange for current read-only venue data remains Wallex Spot only; its existing native OHLCV volume discrepancy is still unresolved, so it does not satisfy the separate global-source requirement.
6. **The currently integrated dashboard does not prove the downstream decision/execution chain.** It has no order-submit route and remains read-only. There is no evidence here of a connected approved feed reaching the real analysis consumer, then a real risk gate, then a venue order adapter, followed by order/fill reconciliation. Do not add a parallel strategy or order path to make the dashboard appear complete.

## Alternative-provider screen

- **CoinAPI** was checked as a potential replacement. Its official OHLCV endpoints require an API key and address a specific `symbol_id` (examples are venue-specific symbols such as `BITSTAMP_SPOT_BTC_USD`); its OHLCV values are derived from trades. The official FAQ describes its Exchange Rates API as a 24-hour rolling VWAP across curated markets/pairs, but that is not an OHLCV candle series with equivalent traded-volume semantics. Therefore CoinAPI may be a candidate for a separate aggregated price/reference feed, but it is **not yet a verified replacement for the required common OHLCV+volume source**. No HES credential, active plan, permitted-use confirmation, or raw response is available here. Sources: https://www.coinapi.io/products/market-data-api/docs/rest-api/ohlcv/ohlcv/symbol_id/history/get ; https://www.coinapi.io/products/market-data-api/faq ; https://www.coinapi.io/products/exchange-rates-api/faq
- A single venue's public candles (including Binance) can be useful as an explicitly labelled comparison/control source, but cannot be called a global aggregate or silently used as the analysis feed while execution is isolated to Wallex. The open Binance adapter PR is venue-specific; it does not close the provider-selection requirement.

## Required acceptance evidence before source approval

- Provider identity, global-versus-venue scope, aggregation methodology, included venues/markets, instrument mapping, price denomination, and permitted use are supported by current primary sources.
- Real HES-authorized access is demonstrated with the correct subscription/permission and key held outside source control; record HTTP status/headers (redacting secrets), retrieval UTC, request parameters, exact raw response bytes, and SHA-256.
- Receive raw BTC, ETH, and SOL responses from the same documented product and instrument class. Explain timestamp unit/timezone, candle open/close/finality, base volume, quote volume, trade count, empty-period fill policy, and aggregation rules from provider docs plus observed payloads.
- Compare BTC, ETH, and SOL on an identical, pinned UTC window and resolution. Preserve source payloads/hashes; quantify timestamp, OHLC, volume, missing-bar, and closed-candle differences. Do not silently rescale or infer volume semantics.
- Test malformed/error/unauthorized/stale responses, duplicate timestamps, out-of-order bars, missing intervals, symbol mapping, and failure/recovery behavior.
- Confirm price denomination and source-to-execution venue basis separately; global USD reference prices must not be labelled executable USDT quotes.
- Wire exactly the accepted source through the existing canonical candle bridge to both the existing chart datafeed and the actual analysis consumer, preserving source/version/UTC/lineage. Do not create a second candle engine or parallel frontend.
- Prove the actual analysis output reaches the existing risk gate; prove risk rejection prevents order-adapter invocation; then, only in an explicitly authorized sandbox/test environment, prove client-order idempotency, timeout/unknown-order recovery, venue order status, partial/full fills, fees, and reconciliation. Use a fake/test adapter until sandbox access and approval are evidenced; do not send live orders.
- Keep chart display, analysis approval, risk approval, order adapter, and execution reconciliation as separate acceptance gates. Passing a parser test or smoke request is not evidence for downstream gates.

## Safety decision

Until all applicable evidence is accepted, this feed remains **display-only reference data**. Keep `HOLD / NO_TRADE_ONLY`, `live_execution_enabled=false`, and all volume-dependent strategy features disabled. No merge, deployment, collector activation, credential use, private endpoint, or live order is authorized by this ADR.
