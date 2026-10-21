# Market-data provider qualification gates

Status date: 2026-10-21

## Decision

- Primary vendor to qualify: Kaiko.
- Fallback candidate: CoinAPI.
- Neither vendor is approved for production until every gate below has evidence.
- TradingView Lightweight Charts is a rendering library, not the market-data entitlement.
- Exchange execution APIs remain separate from the canonical chart/analysis feed.
- Existing Yahoo Finance data remains provisional and must not be promoted to strategy-grade data by assumption.

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
