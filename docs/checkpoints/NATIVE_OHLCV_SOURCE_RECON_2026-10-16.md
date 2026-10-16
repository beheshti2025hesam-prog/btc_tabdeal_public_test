# Native OHLCV Source Reconnaissance — Tabdeal
**Date:** 2026-10-16  
**Base main SHA reviewed:** `4956cf519c445edd004fdd4e763bdb3347a7ada9`  
**Disposition:** `RESEARCH ONLY / NO RUNTIME CHANGE / HOLD`

## Executive result
The current project does not have verified native OHLCV ingestion. The official public sources reviewed in this pass do not establish a documented Tabdeal kline/candlestick REST method. Therefore, do not guess an endpoint or label trade-derived candles as native exchange candles.

## Evidence inspected
1. Project source:
   - `core/data_engine/candles.py` implements aggregation from canonical trades.
   - `forward/market_data_contract_v1.json` declares `CONTRACT_ONLY` and defines normalization of trade observations.
   - `forward/market_data_README.md` explicitly says this reference layer is not wired into the live collector.
   - `forward/forward_tabdeal_ingestion_v1.py` normalizes supplied trade records and makes no network request.
2. Official Tabdeal API documentation: https://docs.tabdeal.org/
   - Public market sections inspected include depth, trades, exchangeInfo, ping/time and WebSocket descriptions.
   - Search of the rendered official documentation found no `klines`, `candlestick`, or `کندل` entry.
3. Official Tabdeal Python SDK:
   - Repository: https://github.com/Tabdeal-Exchange/tabdeal-python
   - Public `tabdeal/spot.py` and `tabdeal/future.py` were inspected; no method named for kline/candle/OHLCV was found in these files.
4. Official Tabdeal Postman collection:
   - Repository: https://github.com/Tabdeal-Exchange/tabdeal-api-postman
   - Public collection search found no `kline`, `Kline`, or `candle` entry.

## What this evidence does and does not prove
- Supported: a documented native OHLCV endpoint was not found in the reviewed official documentation, SDK source files, or official Postman collection.
- Not supported: that Tabdeal has no private, undocumented, UI-internal, or newly added candle endpoint. Absence from these sources is not proof of nonexistence.
- Not supported: parity between the current trade-derived candles and the official chart.
- No HTTP call to an inferred candle endpoint was made, because inventing a path would produce weak evidence and risk false conclusions.

## Safe implementation gate
Do not implement a Tabdeal native candle client until an endpoint/contract is supported by an authoritative source or a verified official response. Do not use UI-internal endpoints as a production contract without explicit verification and stability/security review.

## Next actions — forward only
1. Ask Tabdeal support for the official public OHLCV/kline endpoint or SDK method, supported markets, intervals, response schema, timestamp convention, closed/open-candle semantics, pagination/retention and rate limits.
2. In parallel, inspect the public website's chart data contract only as discovery evidence, not as an approved production API.
3. Once an authoritative endpoint is identified, build a read-only adapter preserving source strings/Decimal precision and timestamps.
4. Add adversarial tests: malformed rows, non-finite/negative values, duplicate candles, missing intervals, non-monotonic timestamps, interval-boundary alignment, open-vs-closed candle handling and no-future-data.
5. Compare a bounded sample against the official chart at the same symbol/timeframe and document timezone/tolerance rules.
6. Keep trade-derived aggregation as a separate cross-check, not as a substitute for native candles.
7. Run checks on the exact candidate SHA; keep the work on a separate branch until reviewed.

## Safety
No production code, strategy, historical evidence, collector state, deployment, or exchange order was changed. Current disposition remains `HOLD / NO_TRADE_ONLY`.


## Anti-duplication check against prior project history
Prior HES investigation dated 2026-09-05 already tested the likely Tabdeal Kline paths on `api.tabdeal.org` and `api1.tabdeal.org`, including `/api/v1/klines`, `/fapi/v1/klines`, `/api/v1/fapi/klines`, and futures read-path variants. The recorded responses were HTTP 404. Do not repeat these same endpoint probes unless a new authoritative contract or changed API version gives a reason. Prior checks also confirmed public Futures `ping`, `time`, `exchangeInfo`, and `depth` endpoints can respond successfully; that does not establish OHLCV support.

## Updated next action
Because the likely endpoint guesses have already failed and the reviewed official references still do not document Klines, the next high-value step is to obtain an authoritative answer through Tabdeal's currently verified support channel or a newly published official contract. Do not reuse the previously reported failed `info@tabdeal.org` address. In parallel, native OHLCV support may be implemented for another venue only as a clearly separated venue adapter; never label that as Tabdeal chart parity.


## Additional route check — public Binance OHLCV
On 2026-10-16, official Binance documentation was verified to document public Spot klines at `GET /api/v3/klines`; the market-data-only domain `data-api.binance.vision` documents unauthenticated public `/api/v3/klines` access. The Binance tool also returned sample Spot and USDⓈ-M Futures 1m candles plus recent Spot trades without user credentials. This establishes that a separate Binance OHLCV adapter is technically plausible without a personal API key.
- Official docs: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
- Market-data-only docs: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md

## Timestamp interpretation correction and live diagnostic — 2026-10-16
The earlier interpretation of timestamps around `1792160580000` ms as 2026-11-16 UTC was incorrect. These timestamps correspond to 2026-10-16 UTC, consistent with the checkpoint date. Do not retain the earlier future-date claim.

A read-only GitHub Actions probe ran at commit `7146fcf3b43b33e35e19c32fdd7eac1bef1b1124` (PR #296). Its Spot sample reported server time `1792161245762` ms, local midpoint `1792161245501` ms, server/local skew `261` ms, and latest candle age `5762` ms. Spot passed the implemented clock-skew and candle-freshness checks. This single sample does not prove ongoing reliability or historical/chart parity, but it removes the earlier claim that this timestamp was future-dated relative to 2026-10-16.

The same diagnostic received `HTTP 451` from the USDⓈ-M Futures public endpoint in the GitHub-hosted runner. Futures status is **BLOCKED / UNVERIFIED**; this is consistent with an access/geographic restriction in that execution environment and does not establish an upstream Binance data fault. The diagnostic remains fail-closed when either venue cannot be verified. Unit tests passed, while the combined live diagnostic job failed on the Futures 451 response.

## Revised recommendation
No personal API key is needed for public Binance candles. Do not request or accept the user's API secret. A separate read-only Binance Spot adapter may proceed only with continued timestamp/schema validation and independent samples; USDⓈ-M Futures ingestion remains blocked until it can be verified from an authorized, suitable network environment. Neither venue may be represented as Tabdeal chart parity. Tabdeal-native OHLCV remains undocumented in the official sources reviewed.
