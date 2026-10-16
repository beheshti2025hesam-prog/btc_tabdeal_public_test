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
5. Deterministic tests using fake HTTP responses; tests do not hit a live endpoint.

## Deliberate limits

- No collector is enabled and no background/live process is started.
- No credentials, private account data, order endpoints, or execution code are used.
- No chart parity is claimed until same-window OHLC and timestamp comparisons are captured and reviewed.
- Other exchanges and brokers require explicit official-source adapters; they are not inferred from Binance.
- The existing Tabdeal trade-derived path is not silently promoted as the primary path by this adapter.

## Required next validation

Fetch the same closed BTCUSDT 15m window from Binance Spot uiKlines, Spot klines, and USDⓈ-M Futures klines; compare Spot OHLC and timestamps exactly, record documented volume differences separately, and keep Spot/Futures product data separate.
