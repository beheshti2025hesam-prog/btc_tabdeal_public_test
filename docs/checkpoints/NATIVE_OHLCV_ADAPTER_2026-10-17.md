# Native OHLCV adapter implementation checkpoint

- Date: 2026-10-17
- Base: main at SHA 4956cf519c445edd004fdd4e763bdb3347a7ada9
- Scope: read-only native candle adapter and deterministic tests.
- Primary path decision: exchange/broker-provided OHLCV; trade aggregation is secondary only.

## Implemented in this branch

1. Binance Spot chart-optimized uiKlines.
2. Binance Spot standard klines for parity checks.
3. Binance USDⓈ-M Futures klines.
4. Raw response SHA-256, Decimal precision, closed-candle filtering, malformed-row rejection, duplicate conflict handling, explicit intra-window gaps, and no synthetic candles.
5. Disabled-by-default durable append-only one-shot collector with explicit fsync and source digest.
6. NativeOHLCVForwardRunnerV1 writes one fully validated batch to the immutable forward journal without depending on trade.sequence.
7. Deterministic tests use fake HTTP responses; tests do not hit a live endpoint.

## Deliberate limits

- No collector is enabled and no background/live process is started.
- No credentials, private account data, order endpoints, or execution code are used.
- A five-candle Spot comparison found exact open/close timestamp and OHLC matches between standard klines and uiKlines, but the final candle's volume differed (48.29596000 vs 48.29630000; trade count 5246 vs 5247). Full volume/chart parity remains unverified.
- The comparison came from structured connector output; raw HTTP bytes and their hashes were not preserved in that evidence artifact.
- Other exchanges and brokers require explicit official-source adapters; they are not inferred from Binance.
- The existing Tabdeal trade-derived path is not silently promoted as the primary path by this adapter.

## Required next validation

Repeat the bounded BTCUSDT 15m Spot comparison through the new direct HTTP adapter, preserve raw-response SHA-256 values, investigate the one-bar volume discrepancy, and compare Spot and USDⓈ-M Futures only within their own product identity. Add each selected broker through an official endpoint/SDK once its identity and chart contract are established.
