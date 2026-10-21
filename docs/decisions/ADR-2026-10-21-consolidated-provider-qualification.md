# Consolidated market-data provider qualification — 2026-10-21

## Decision

**NOT APPROVED FOR PRODUCTION — provider access, exact product, and HES-use rights remain unverified.**

The target architecture is fixed:
- one independently qualified market-data source feeds the canonical candle bridge;
- the exact same validated UTC candle batch feeds the chart and the existing analysis consumer;
- one analysis engine;
- execution exchange adapters are used for executable venue prices/constraints, order submission, order state, fills, and reconciliation only;
- do not recreate exchange charts, aggregate venue candles locally, synthesize bars, round timestamps, or rescale volume;
- investigate venue-data discrepancies only when evidence connects them to execution, risk, or order/fill reconciliation.

## Provider screen

### CoinAPI — best documented candidate to qualify next; not yet accepted

Official documentation:
- OHLCV history: https://docs.coinapi.io/market-data/rest-api/ohlcv/historical-data
- OHLCV overview: https://docs.coinapi.io/market-data/rest-api/ohlcv
- Usage policy: https://www.coinapi.io/usage-policy
- Product overview: https://www.coinapi.io/rest-api

Evidence from public docs:
- The OHLCV history endpoint returns ascending time-series bars with period start/end, OHLC prices, and traded volume.
- Its historical OHLCV endpoint is keyed by a specific `symbol_id`; documentation examples include exchange-specific symbols. This endpoint alone does not establish a cross-venue aggregated candle for a given pair.
- CoinAPI describes its Exchange Rates API as aggregated multi-market rates/VWAP, but a reference-rate time series must not be silently treated as OHLCV with traded-volume semantics.
- CoinAPI's published usage guidance distinguishes internal trading systems from customer-facing distribution; customer-facing display may require additional licensing.
- No HES-owned API key, active plan, actual response, chosen symbol mapping, SLA, or written confirmation covering the exact intended chart + automated analysis use is present in the reviewed repository evidence.

Result: a candidate for provider qualification, **not an approved drop-in replacement**. Do not write a production adapter against an assumed symbol/aggregation or claim real access without an authenticated raw response.

### CoinDesk / CCCAGG — not approved on public evidence alone

The existing source-qualification ADR records that public plan descriptions and API licensing do not establish permission for HES's trading-related analysis use, and a selected-exchange OHLCV endpoint is not automatically an aggregate. Written product-specific permission and a current authenticated representative response would be required before reconsideration.

### TradingView — chart library, not the data provider

Official docs: https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/

The charting library needs an application-supplied datafeed. Use the existing HES bridge as that boundary. Do not scrape the hosted TradingView website or treat a chart embed as a programmatic analysis feed.

### Yahoo Finance — display-only provisional source

The existing adapter's public endpoint is unofficial and its aggregate provenance, volume semantics, entitlement, and SLA remain unverified. The latest live smoke has rejected a candle timestamp that is not aligned to the requested interval. Preserve fail-closed validation; do not round or shift that timestamp. Yahoo must not feed strategy decisions.

## Integration contract after provider approval

1. Store the provider key in the runtime secret manager/environment; never commit credentials.
2. Use the provider's documented consolidated/reference OHLCV product, not a venue-specific symbol unless the product contract explicitly defines that as the approved common source.
3. Map only verified provider symbol identifiers for required instruments and intervals (at minimum BTC/USDT 1m and 1h, plus other explicitly supported project instruments).
4. Normalize only representation: UTC timestamps, decimal values, and the existing canonical candle type. Do not manufacture missing bars or change reported volume.
5. Reject malformed OHLC, non-finite/negative values, duplicate/out-of-order or interval-misaligned timestamps, stale data, incomplete/unsupported symbol mappings, and provider failures. Fail closed.
6. Feed the same immutable validated candle batch (same source ID, symbol, interval, UTC boundaries, OHLCV) to the existing chart and actual analysis consumer. Add a test asserting identity of that batch; do not add a second strategy or candle engine.
7. Verify analysis -> existing risk gate -> existing venue execution adapter -> order acknowledgement/state -> fills -> reconciliation in an authorized sandbox. Test idempotency, partial fills, rejects, timeouts, stale signal, price/quantity filters, and venue quote/spread/slippage checks.
8. Keep live order submission disabled until provider rights/access, exact-head CI, source freshness/volume semantics, real analysis wiring, and sandbox execution/reconciliation evidence are all approved.

## Evidence and blocker checklist

- [x] Architecture scope clarified and recorded in PR #340 and PR #320 discussions.
- [x] Official provider docs screened for CoinAPI, CoinDesk, TradingView.
- [x] Existing HES bridge and current source limitations inspected.
- [ ] Provider subscription/API credential supplied and tested from HES runtime.
- [ ] Written confirmation of permitted internal chart + algorithmic trading-decision use for the exact selected product.
- [ ] BTC/USDT (or provider-defined equivalent) 1m and 1h raw payloads validated; volume definition documented.
- [ ] Approved provider wired through the existing canonical bridge; identical batch proven at chart and real analysis consumer.
- [ ] Exact-head CI and live smoke pass without timestamp rounding or weakening validation.
- [ ] Authorized sandbox order lifecycle and reconciliation tests pass.

## Current runtime status

`HOLD / NO_TRADE_ONLY`. This document does not approve the provider, claim integration is complete, or enable deployment/live trading. Do not claim the full task is complete while required access, licensing, raw-response, and execution-chain evidence are missing.
