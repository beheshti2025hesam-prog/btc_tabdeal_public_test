# Provider screen — consolidated crypto OHLCV for HES
**Date:** 2026-10-21  
**Status:** SCREEN COMPLETE / SOURCE APPROVAL BLOCKED  
**Scope:** Select an existing, licensed data product for one canonical chart + analysis candle bridge. This is a provider screen, not an implementation of an aggregation engine.

## Decision

No reviewed candidate currently satisfies all three required gates with evidence in hand:

1. A documented, multi-venue/global consolidated OHLCV candle product (not one exchange's candles or a price-only index);
2. explicit semantics for base volume, quote volume, venue coverage, empty intervals, candle boundaries/finality, and aggregation methodology;
3. a valid HES entitlement plus written permission for internal chart display and algorithmic/trading decision input.

Do not create a bespoke multi-exchange aggregator to compensate for a provider product gap. Keep the existing canonical candle bridge and chart renderer; replace only the upstream provider once a qualifying product is licensed and its payload is verified. Until then, keep the source display-only, `HOLD / NO_TRADE_ONLY`, and live execution disabled.

## Evidence-based candidate screen

| Candidate | What official material supports | Gap against HES requirement | Decision |
|---|---|---|---|
| CoinAPI Market Data API | OHLCV is available by a specific `symbol_id`; its FAQ says OHLCV, trades and order books are exchange-specific, not cross-exchange aggregated. Its usage guidance says internal trading systems and internal dashboards are generally internal use, while customer-facing display may need separate licensing. | It does not supply the required consolidated global OHLCV series as a ready-made candle feed. Building that from venue-specific feeds would create an HES aggregation engine and require a methodology decision. | **Not the common-source solution as currently documented.** Could be reconsidered only if CoinAPI confirms a specific existing consolidated OHLCV product and its terms in writing. |
| Coin Metrics Market Data Feed | Paid API provides candles from market-level data; documentation defines a market as a specific pair/contract on a specific exchange. Candles are derived from trades and are omitted for intervals with no underlying trades; gaps are expected. Community API exists, but most endpoints require a key. | The reviewed candles are market-specific rather than a documented global consolidated OHLCV candle series. Gap policy is documented, but it does not solve global aggregation or licensing for HES's intended use. | **Not qualified as the global candle source.** Potential independent venue-level comparator only, subject to access/terms. |
| Kaiko L1/L2 market data | Official product pages describe normalized live and historical spot/derivatives data across 100+ exchanges, with API/stream delivery and aggregation products. | The reviewed dedicated Display licensing page explicitly says its data is for display and not an input to financial calculations, trading, or settlement. That product is therefore not suitable as HES's analysis input. A different licence/product would need written confirmation. | **Display product rejected for strategy input.** Ask for a different expressly licensed analytics/trading-input product only if pursuing Kaiko. |
| CoinDesk Data / CCCAGG | Data API has spot historical-minute endpoints and CCCAGG/reference-data products; API access requires an active key/subscription. | The existing ADR records the public API licence as restricting use and stating API data is not intended for trading purposes; current entitlement and written permission are absent. A venue-specific spot endpoint is not automatically a consolidated series. | **Blocked on terms and entitlement.** Do not use for HES decisions absent a written exception/licence. |
| Yahoo Finance public chart endpoint | Raw read-only captures were recorded in `evidence/market_data_source_audit_20261020.json`. | Unofficial endpoint; provider aggregation provenance and volume semantics unverified; observed off-minute timestamps and null/populated endpoint differences; latest volume was zero. A fresh probe on the observation host returned HTTP 429. | **Reference-only; not accepted for analysis.** Keep fail-closed validation. |
| Binance public klines | Venue-specific public OHLCV can serve as an independent comparison source when reachable. | It is a single venue, not a global consolidated feed. The observation host's previous requests failed with network-unreachable errors; the 2026-10-21 probe timed out (HTTP 000). | **Comparison source only; not the global source.** |

## Official references reviewed

- CoinAPI usage policy: https://www.coinapi.io/usage-policy
- CoinAPI OHLCV by symbol: https://www.coinapi.io/products/market-data-api/docs/rest-api/ohlcv/ohlcv/symbol_id/history/get
- CoinAPI FAQ, including explicit statement that OHLCV/trades/order books are not aggregated across exchanges: https://www.coinapi.io/products/market-data-api/faq
- Coin Metrics API v4, market candles and market-level definitions: https://docs.coinmetrics.io/api/v4/
- Coin Metrics market data overview: https://docs.coinmetrics.io/market-data
- Kaiko L1/L2 product overview: https://www.kaiko.com/products/l1-l2-data
- Kaiko display licence scope: https://www.kaiko.com/resources/display
- CoinDesk source/permission review and raw-probe evidence: `docs/decisions/ADR-2026-10-20-market-data-source-qualification.md` and `evidence/market_data_source_audit_20261020.json`

## Required next step — no code workaround

Request a written quote and product/use confirmation from vendors for an existing product matching this exact specification:

- consolidated multi-venue spot OHLCV for BTC, ETH and SOL with a documented venue universe and weighting/aggregation method;
- base-volume and quote-volume definitions, treatment of duplicate/outlier trades, zero-trade intervals, late/corrected trades, and candle finality;
- live plus historical REST/WebSocket access with UTC interval boundaries and explicit source timestamps;
- permission for HES's internal dashboard display **and** automated strategy/risk calculations/trading-related decision support;
- explicit statement whether the feed is a reference/index series or a traded-volume series, and whether any raw/normalized values may be exposed to HES users;
- access credentials and service/retention/rate-limit terms, held in a secret store—not source control or chat.

After entitlement is provisioned, capture raw BTC/ETH/SOL responses, hash the exact bytes, compare against an independent source on the same pinned UTC windows, and verify candle and volume semantics before changing the provider behind the existing bridge. Do not round timestamps, rescale volume, fill gaps, or relabel a venue-specific feed as global.

## Runtime disposition

- Existing TradingView Lightweight Charts integration remains a renderer only; it does not supply market data.
- Yahoo remains a provisional display reference only.
- No production analysis connection is approved for this feed.
- No new candle engine, second frontend, synthetic aggregate, collector activation, deployment, merge, or live order is authorized by this screen.
- Acceptance remains **BLOCKED** until product scope, written rights, authenticated payload evidence, independent parity, and existing analysis-bridge integration are demonstrated.
