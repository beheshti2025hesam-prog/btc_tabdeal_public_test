# Market-data provider qualification gates

Status date: 2026-10-21

## Decision

- Primary vendor to qualify: Kaiko.
- Fallback candidate: CoinAPI.
- Neither vendor is approved for production until every gate below has evidence.
- TradingView Lightweight Charts is a rendering library, not the market-data entitlement.
- Exchange execution APIs remain separate from the canonical chart/analysis feed.
- Existing Yahoo Finance data remains provisional and must not be promoted to strategy-grade data by assumption.

## Public product facts checked on 2026-10-21 (not a qualification decision)

- Kaiko's published Level 1 Aggregations tier includes OHLCV and is advertised from **USD 1,000/month per ticker pack**. Kaiko lists OHLCV through REST and Stream, with 1-second to 1-day granularity and historical availability. This is a public starting price, not a quote for HES's required symbols, history, or intended use: [Kaiko Level 1 & Level 2 data](https://www.kaiko.com/products/l1-l2-data), [Kaiko OHLCV product](https://www.kaiko.com/collections/ohlcv).
- Kaiko's separate Display offering explicitly describes use for charts and reference context **without** using the data as input to financial calculations, trading, or settlement. HES must not treat a display-only license as sufficient for strategy inputs: [Kaiko Display licensing](https://www.kaiko.com/resources/display).
- CoinAPI documents normalized REST and WebSocket market-data products, including OHLCV. Its Market Data API documentation lists a Free plan at 1 request/second and 100 requests/day; the pricing page says WebSocket is not included in the Free plan. A no-cost REST trial therefore does not by itself meet the continuous live-stream requirement: [CoinAPI Market Data API](https://www.coinapi.io/products/market-data-api/docs/how-to-guides/real-time-trades-stream-using-websocket-with-different-languages), [CoinAPI pricing](https://www.coinapi.io/products/market-data-api/pricing).
- On the authorized HES VPS, the CoinAPI host was reachable at the HTTPS layer but returned HTTP 401 without authentication. The expected `/etc/hes-trade-agent/coinapi.env` file was absent; no credential was read or exposed. This proves connectivity only, not entitlement or usable data access.
- The same VPS resolves `api.binance.com`, `fapi.binance.com`, and `stream.binance.com` to `10.10.34.34`, where HTTPS connections time out; `data-api.binance.vision` returns HTTP 451. Do not work around these network or access controls. Any future network change must be approved by the host/network operator.

## Delivery gates

### Gate 1 — commercial and legal rights
Obtain written confirmation for the exact product and series that HES will use:
- internal algorithmic analysis, indicators, backtesting and paper trading;
- in-app chart/candle display for intended users;
- caching and retention duration;
- derived outputs/signals, redistribution restrictions, and any separate display license.

Store the vendor response and applicable contract/product schedule as review evidence. Public documentation alone does not prove HES has a license or entitlement.

### Gate 2 — instrument and series identity
Vendor must identify, in writing:
- exact product, endpoint/protocol, instrument IDs and symbol mapping;
- venue-specific versus consolidated/benchmark series;
- BTC and ETH spot plus perpetual-futures coverage;
- 1-minute and 1-hour OHLCV availability and history depth;
- timestamp timezone and candle-boundary semantics;
- volume units (base/quote/contracts), trade corrections/revisions, and late-arriving data.

Do not assume a cross-venue index is equivalent to traded OHLCV volume. Do not rescale volume or shift candle timestamps to force a match.

### Gate 3 — authenticated read-only trial
With authorized trial credentials, archive representative raw REST and streaming payloads, request metadata, retrieval timestamps, and errors for BTC/ETH spot and perpetual instruments. Never commit credentials or secrets.

### Gate 4 — deterministic quality checks
Test freshness, reconnect/replay, missing and duplicate bars, revisions, OHLC invariants, timestamp boundaries, symbol mapping, volume units, and consistency against the vendor's underlying trade data where available. Define measurable thresholds before examining the outcome.

### Gate 5 — same-batch chart/analysis proof
Use the existing frontend and analysis path. Both consumers must receive the same immutable batch identity for the same instrument, interval, and closed-candle window. Archive a reproducible comparison report. Any unexplained mismatch blocks cutover.

### Gate 6 — paper execution and reconciliation
Only after data gates pass, run an authorized exchange sandbox test: signal -> risk boundary -> paper/sandbox order -> order/fill updates -> fees/filled quantity/average price reconciliation. This does not authorize live trading.

## Current evidence boundary

- An email requesting trial access and written licensing clarification was sent to Kaiko Sales on 2026-10-21; a successful send-tool response is not proof of delivery or a vendor reply.
- No vendor reply, contract grant, credentials, authenticated raw payload, or production-quality result is recorded here.
- Do not report provider qualification, end-to-end readiness, or live execution as complete without evidence for the corresponding gate.

## Release rule

Until all required gates pass and are reviewed, runtime status remains `HOLD / NO_TRADE_ONLY` and `live_execution_enabled=false`.
