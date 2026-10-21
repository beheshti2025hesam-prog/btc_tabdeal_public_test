# Consolidated market-data provider qualification — 2026-10-21

## Decision

**NOT APPROVED FOR PRODUCTION — provider access, exact product, market/volume semantics, and HES-use rights remain unverified.**

The target architecture is fixed:
- one independently qualified market-data provider feeds the canonical candle bridge;
- the exact same validated UTC candle batch feeds the chart and the existing analysis consumer;
- one analysis engine;
- execution exchange adapters are used for executable venue prices/constraints, order submission, order state, fills, and reconciliation only;
- do not recreate exchange charts, aggregate venue candles locally, synthesize bars, round timestamps, or rescale volume;
- investigate venue-data discrepancies only when evidence connects them to execution, risk, or order/fill reconciliation.

## Provider screen (official public documentation reviewed 2026-10-21)

### Kaiko — strongest commercial lead to qualify next; not yet accepted

Official evidence:
- Market-data products and use cases: https://www.kaiko.com/products/l1-l2-data
- Data dictionary / OHLCV availability: https://docs.kaiko.com/explore-our-data/data-dictionary
- Channel availability: https://docs.kaiko.com/explore-our-data/subscriptions-channel-availability
- Display-only licence is explicitly not for backend financial calculations, trading, or settlement: https://www.kaiko.com/resources/display
- Market-data pricing shown publicly starts at $1,000/month for Level 1 Aggregations: https://www.kaiko.com/products/l1-l2-data

What the evidence supports:
- Kaiko documents normalized OHLCV with REST granularity from 1 second to 1 day and historical coverage, plus real-time streaming.
- Its data catalog and examples support multi-exchange market-data queries, but a wildcard query or normalized API is not proof that one returned OHLCV series is a consolidated cross-venue candle.
- Kaiko's display-only product is explicitly unsuitable as the input to HES's strategy calculations. A display licence cannot be reused for the analysis engine.
- The exact licensed product, whether it supplies a single consolidated OHLC series for BTC/USDT (or a defined equivalent), volume units/meaning, intended algorithmic use rights, service levels, and account entitlement must be confirmed in writing.

Result: **first commercial provider to request exact product/licensing confirmation from**, not an approved source and not permission to implement against assumed semantics.

### CoinDesk / CCIX (formerly CCCAGG) — aggregate price/index candidate, licence blocker

Official evidence:
- CCIX index description and minute/hour OHLCV+ endpoints: https://developers.coindesk.com/documentation/data-api/index_cc
- Plan limits and licence categories: https://developers.coindesk.com/pricing/
- API licence agreement (22 April 2026): https://data.coindesk.com/api-licence-agreement

What the evidence supports:
- CoinDesk documents CCIX as a multi-market aggregated reference-price index and provides minute/hour historical OHLCV+ index endpoints.
- The published API licence says the default licence is for internal use and, absent written permission, prohibits display and use in connection with an Index or Financial Product. The agreement also states the data is not intended for trading purposes.
- Therefore public endpoint availability or a personal/non-commercial plan is not adequate permission for HES chart display plus automated trading decisions. Any reconsideration requires a written product-specific licence/exception and clarification of index OHLC versus volume fields.

Result: **not approved on public evidence**; do not treat index OHLCV+ as executable venue OHLCV or assume its volume is a consolidated traded-volume series.

### CoinAPI — not a consolidated OHLCV drop-in based on current docs

Official evidence:
- OHLCV history: https://docs.coinapi.io/market-data/rest-api/ohlcv/historical-data
- OHLCV overview: https://docs.coinapi.io/market-data/rest-api/ohlcv
- Official FAQ on aggregation and volume: https://www.coinapi.io/products/market-data-api/faq
- Usage policy: https://www.coinapi.io/usage-policy

The current FAQ explicitly says OHLCV, order-book and trade datasets are per symbol and per exchange, not aggregated across exchanges. Its aggregated Exchange Rates API provides multi-venue VWAP/reference rates, but that is not automatically a candle series with meaningful traded-volume semantics. Do not implement a multi-venue candle builder inside HES to work around this; that would violate the project's single-provider/no-local-aggregation rule.

Result: **not a drop-in consolidated OHLCV provider** on the reviewed public evidence. Reconsider only if CoinAPI identifies a specific separately licensed product whose documented output meets the exact contract.

### Binance public Spot klines — technically testable, architecturally not approved

PR #339 implements and tests a public Binance Spot kline reader with explicit venue identity, closed-candle checks, Decimal parsing, freshness checks, and unchanged volume. This is useful as a parser/bridge test fixture, but Binance Spot is one venue, not an independent consolidated market source. Passing its tests or smoke test does not qualify it as the HES analytical source. Keep PR #339 non-production unless the architecture decision is explicitly changed.

### TradingView — charting client, not the data provider

Official docs: https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/

The charting library requires an application-supplied datafeed. Use the existing HES bridge as that boundary. Do not scrape the hosted TradingView website or treat a chart embed as a programmatic analysis feed.

### Yahoo Finance — display-only provisional source

The existing adapter's public endpoint is unofficial and its aggregation provenance, volume semantics, entitlement, and SLA remain unverified. The exact tested dashboard head's live smoke failed closed with `MarketDataError: candle_timestamp_not_interval_aligned_342`. Preserve fail-closed validation; do not round or shift that timestamp. Yahoo must not feed strategy decisions.

## Integration contract after provider approval

1. Obtain written confirmation of the exact product, permitted internal chart display and automated analysis/trading-decision use, market coverage, service levels, and any restrictions. Do not put credentials in Git.
2. Validate the provider's actual authenticated raw product response; record product/plan, symbol or index identifier, source timestamps, volume fields/units, and all applicable terms.
3. Verify BTC/USDT (or a documented provider equivalent) at 1m and 1h. If the provider offers only an index/reference OHLC series, do not label it venue-traded OHLCV; document whether volume-dependent analysis is unavailable.
4. Normalize representation only: UTC timestamps, decimal values, and the existing canonical candle type. Do not manufacture missing bars, aggregate venues locally, round timestamps, or change reported volume.
5. Reject malformed OHLC, non-finite/negative values, duplicate/out-of-order or interval-misaligned timestamps, stale data, incomplete/unsupported mappings, and provider failures. Fail closed.
6. Feed the same immutable validated candle batch (same source ID, symbol/index, interval, UTC boundaries, OHLCV fields) to the existing chart and actual analysis consumer. Add a test asserting batch identity; do not add a second strategy or candle engine.
7. Verify analysis -> existing risk gate -> existing venue execution adapter -> order acknowledgement/state -> fills -> reconciliation in an authorized sandbox. Test idempotency, partial fills, rejects, timeouts, stale signal, price/quantity filters, and venue quote/spread/slippage checks.
8. Keep live order submission disabled until provider rights/access, exact-head CI, source freshness/volume semantics, real analysis wiring, and sandbox execution/reconciliation evidence are all approved.

## Evidence and blocker checklist

- [x] Architecture scope clarified and recorded in PR #340 and PR #320 discussions.
- [x] Official public docs screened for CoinAPI, CoinDesk, TradingView, and Kaiko.
- [x] Exact-head dashboard CI failure inspected; 17 deterministic tests passed, live smoke failed closed.
- [x] PR #340 moved back to Draft and blocker recorded; no timestamp rounding workaround.
- [ ] Provider subscription/API credential supplied and tested from HES runtime.
- [ ] Written confirmation of permitted internal chart + algorithmic trading-decision use for the exact selected product.
- [ ] BTC/USDT (or provider-defined equivalent) 1m and 1h raw payloads validated; volume definition documented.
- [ ] Approved provider wired through the existing canonical bridge; identical batch proven at chart and real analysis consumer.
- [ ] Exact-head CI and live smoke pass without timestamp rounding or weakening validation.
- [ ] Authorized sandbox order lifecycle and reconciliation tests pass.

## Current runtime status

`HOLD / NO_TRADE_ONLY`. This document does not approve a provider, claim integration is complete, or enable deployment/live trading. Do not claim the full task is complete while required access, licensing, raw-response, and execution-chain evidence are missing.
