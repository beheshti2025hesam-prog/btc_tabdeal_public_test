# Market-data source qualification — 2026-10-20

## Status

**Open blocker. No production or strategy-approved market-data provider has been established by this PR.** The Yahoo Finance adapter is a provisional, read-only USD reference for chart plumbing and must not be treated as a certified global aggregate or trusted strategy input.

## Evidence-based findings

1. **TradingView is not itself a market-data API for this integration.** Its official Advanced Charts documentation states that the library contains no market data and requires a data source or third-party provider. The Datafeed API is a bridge that the application must implement. See:
   - https://www.tradingview.com/charting-library-docs/latest/connecting_data/
   - https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/
2. **TradingView hosted widgets are not a substitute for a programmatic strategy feed.** Its widget FAQ says widgets do not provide an API for exporting data or indicator values. See:
   - https://www.tradingview.com/widget-docs/faq/data/
3. **Yahoo Finance public chart data remains unqualified.** The endpoint used in this PR is unofficial; this repository has not established its underlying venue composition, global aggregation methodology, volume definition, contractual SLA, or data-use rights. The adapter preserves source volume unchanged, but preservation is not proof of semantic correctness. A live sample returned volume `0`; therefore volume-derived features remain disabled.
4. **CoinDesk Data API is the strongest documented candidate in this review, but is not yet approved or connected.** The current pricing page distinguishes:
   - Personal: non-commercial CC BY-NC-SA 4.0; aggregate REST access; minute history only for the latest hour; lifetime call cap.
   - Start-Up: commercial license, internal-only use, REST/WebSocket; minute history only for the latest 24 hours; contact-based pricing.
   - Enterprise: negotiated license, spot/DEX/derivatives and aggregate/trade/order-book datasets, broader historical access, and SLA/private-delivery options.
   
   Therefore the Personal tier cannot be assumed suitable for HES strategy/live use, and the Start-Up tier's stated internal-only license and 24-hour minute-history window must be checked against the project's actual use and history needs. Do not select a plan or imply commercial rights without the account owner confirming intended use and the provider confirming terms.
   
   The current Spot historical minute endpoint is explicitly for selected exchanges and returns base- and quote-currency volumes; it is **not automatically a cross-market aggregate**. CCCAGG/reference-index data must be requested from the correct documented aggregate/index surface, with instrument definitions and volume fields inspected separately. No API credential, successful authenticated response, or representative raw response is available in this PR, so integration cannot honestly be called verified.
   
   Primary sources:
   - Pricing and plan/license/history limits: https://developers.coindesk.com/pricing/
   - Data API introduction and rate limits: https://developers.coindesk.com/documentation/data-api/introduction
   - Spot OHLCV+ minute endpoint (exchange-specific scope): https://developers.coindesk.com/documentation/data-api/spot_v1_historical_minutes
   - Indices/reference rates OHLCV+ minute endpoint: https://developers.coindesk.com/documentation/data-api/index_cc_v1_historical_minutes
   - CCCAGG methodology (older methodology document; must be checked against current terms): https://www.cryptocompare.com/media/37072230/cccagg_methodology-2020-07.pdf

## Required acceptance evidence before source approval

- Provider identity, aggregation methodology, included venues/markets, instrument mapping, and permitted usage are documented from primary sources.
- BTC, ETH, and SOL are tested across the exact required intervals with aligned UTC windows.
- OHLC consistency, candle closure, timestamp units, duplicate handling, stale-data rejection, missing-bar behavior, and source failures are tested.
- Volume units and semantics are documented and verified against representative raw provider responses; no scale factor or inferred meaning is allowed.
- Independent comparisons use the same instrument definition, interval, and UTC time window; differences are quantified and explained without silently changing values.
- Availability, rate limits, authentication, pricing/licensing, and expected latency are confirmed.
- The same approved feed is used by the chart and the analysis pipeline, with source/version/lineage retained. The execution venue remains isolated and is used only for orders, fills, and venue-specific constraints.

## Safety decision

Until every applicable acceptance item is supported by evidence, this feed is **display-only reference data**. Keep `HOLD / NO_TRADE_ONLY`, `live_execution_enabled=false`, and all volume-dependent strategy features disabled. Do not merge/deploy or claim production readiness based only on passing parser tests or a successful smoke request.
