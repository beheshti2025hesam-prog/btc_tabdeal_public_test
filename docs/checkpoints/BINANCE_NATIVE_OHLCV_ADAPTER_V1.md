# Native Binance OHLCV adapter v1

Status: **candidate implementation; not wired into the production analysis path**.

## Scope
- Read-only public market data for Binance Spot (\`/api/v3/klines\`) or USDⓈ-M Futures (\`/fapi/v1/klines\`).
- Defaults to BTCUSDT and 15-minute candles.
- Returns closed candles only; the currently forming candle is excluded.
- Preserves source decimal strings and millisecond timestamps; UTC ISO timestamps are available via \`as_dict()\`.
- Does not fabricate missing intervals, call account/order endpoints, use credentials, or activate a collector.

## Safety and limitations
- The endpoint host is selected from a fixed allowlist; arbitrary URLs cannot be supplied.
- HTTP requests have a bounded timeout and errors fail closed.
- This adapter is not yet connected to the canonical market-data reader, chart UI, risk engine, or execution adapter.
- The VPS used for this candidate could not reach Binance during the current validation attempt (\`Network is unreachable\`). Therefore, live endpoint reachability and raw-response provenance are **not verified** by this change.
- Synthetic/mocked tests verify parsing and safety boundaries only. They do not establish chart parity or live-source reliability.

## Acceptance gates before integration
1. Run adapter tests in CI and on the exact candidate SHA.
2. Obtain a successful read-only public kline response from an allowed network and retain raw response/hash, capture time, URL, HTTP status, and request parameters as evidence.
3. Verify closed-candle freshness and gaps using repeated reads, without inventing missing candles.
4. Compare symbol, timeframe, timestamps, OHLCV and volume units against an independent chart/source for a shared closed-candle window.
5. Integrate through the existing canonical data path only after the above gates pass; keep all execution and trading disabled during validation.
