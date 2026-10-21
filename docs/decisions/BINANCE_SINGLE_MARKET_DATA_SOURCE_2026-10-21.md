# HES Trade Agent — Binance as the single chart/analysis market-data source

**Decision date:** 2026-10-21  
**Decision owner:** Project owner  
**Status:** Source selected for integration; runtime/chart acceptance is not yet passed.

## Fixed architecture
- Binance public market data is the selected single upstream source for chart and analytical candle input, initially BTCUSDT.
- A configured HES datafeed instance must use exactly one explicit market identity at a time: `spot` OR `usdm_futures`; do not merge them. Select the intended market in runtime configuration before enabling the chart.
- Binance REST klines provide historical closed-candle backfill; the corresponding Binance WebSocket kline stream provides live updates and a clear `x` finality flag. Reconcile REST history after startup and every reconnect before trusting continuity.
- Existing `forward/native_candle_bridge_v1.py` remains the single canonical normalizer into HES features. Do not create a second candle aggregator or relabel Binance candles as Wallex/Tabdeal.
- The exchange adapter used to place orders and reconcile fills remains authoritative for orders/fills only. Before executing elsewhere, evaluate source-to-execution basis/spread and staleness as execution-risk gates.
- Volume-dependent features remain disabled until the source volume fields are explicitly tested against feature semantics. No arbitrary volume normalization.
- Read-only market-data access requires no trading credentials. No orders, deployment, collector activation, or live trading are enabled by this decision.

## Implementation added in this branch
- `forward/binance_market_data_source_v1.py`: public REST closed-bar retrieval, raw/combined WebSocket kline event parser, explicit Spot/USDⓈ-M URLs, Decimal OHLCV, identity/timeframe validation, payload hash, and a reconnect supervisor that calls a caller-supplied REST reconciliation callback before each connection attempt.
- `tests/test_binance_market_data_source_v1.py`: identity, source separation, Decimal preservation, finality, bad payload, and URL contract tests.
- `.github/workflows/binance-market-data-source-v1.yml`: exact-head focused CI.

## Acceptance still required before calling it complete
1. Pass exact-head CI.
2. Connect the adapter to the existing canonical bridge in the actual runtime; test historical backfill, closed-bar updates, duplicate suppression, gaps, staleness, reconnect, and session isolation.
3. Verify outbound network access from the target HES runtime and perform a direct WebSocket smoke/soak test.
4. Locate the authorized existing frontend entry point. The currently connected repository contains no verified frontend entry point; do not create a parallel frontend or claim the chart is connected until that entry point is supplied/located.
5. Render the selected chart from this datafeed and compare displayed OHLC against a pinned UTC source window.

Until those gates pass, the source is selected and a read-only adapter is implemented, but production chart integration remains `HOLD / NO_TRADE_ONLY`.
