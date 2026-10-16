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
