# HES Trade Agent — Candle Source Audit
**Date:** 2026-10-16  
**Main SHA audited:** `2487008e4e8cf681e33912733690ed6bbe507cf8`  
**Disposition:** Read-only audit; no runtime or trading behavior changed.

## User priority
Native exchange/broker chart and candlestick data (OHLCV) is the primary product path. Sequence semantics are secondary unless a concrete data-integrity dependency requires them.

## Verified repository facts
1. `core/data_engine/candles.py` implements `TradeCandleAggregator`: it builds OHLCV from canonical trades; it is not a native exchange-candle client.
2. `forward/market_data_contract_v1.json` and `forward/market_data_README.md` describe normalization of Tabdeal public trade observations into 15-minute candles. README explicitly says the layer is a reference/contract implementation and is not wired into the live collector.
3. `forward/forward_tabdeal_ingestion_v1.py` converts supplied Tabdeal trade records into closed 15-minute candles. It makes no network request.
4. `forward/forward_tabdeal_collector_v1.py` collects trade-shaped WebSocket events and is disabled by default. It is not an exchange-native OHLCV endpoint client.
5. `evidence/binance_market_data_smoke_2026-10-16.json` records public Binance Spot and USDⓈ-M Futures metadata/recent-trade reads for BTCUSDT. It explicitly says raw HTTP payload was not preserved and WebSocket was not tested. It does not evidence a native kline/candlestick fetch.
6. Existing candle-ingestion tests use synthetic fixtures and verify normalization/closed-candle behavior; they do not establish parity with the exchange UI chart.
7. No code was changed and no new CI run was triggered by this audit.

## Conclusion
The repo contains candle aggregation/normalization foundations, but the inspected evidence does **not** prove that the agent currently fetches native OHLCV candles from the same official exchange/broker endpoint that backs its chart. This is the next concrete work item.

## Next steps — forward only
1. Identify the chosen venue/instrument and its official public kline/candlestick endpoint or SDK.
2. Implement a read-only native OHLCV adapter, preserving source timestamps and numeric precision, and marking open vs closed candles.
3. Add fixtures/tests for malformed rows, duplicates, gaps, timestamp/timeframe alignment, and no-future-data behavior.
4. Compare sampled fetched candles against the venue chart for the same symbol/timeframe, documenting tolerances and timestamp convention.
5. Keep trade aggregation as a secondary cross-check/compatibility path until native OHLCV is validated.
6. Keep all collection/trading activation disabled until data-source and security gates are satisfied.

No claims of live-chart parity, verified native kline ingestion, or trading authorization are made by this audit.
