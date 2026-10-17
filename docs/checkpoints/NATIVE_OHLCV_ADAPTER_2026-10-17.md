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
- Four closed Spot candles matched exactly across standard klines and uiKlines for timestamps, OHLC, volume, and trade count.
- The fifth candle was still open during the source calls and changed between requests. It is excluded from parity assessment; its changing volume/count is not evidence of a closed-candle discrepancy.
- The comparison came from structured connector output; raw HTTP bytes and their hashes were not preserved in that evidence artifact.
- Other exchanges and brokers require explicit official-source adapters; they are not inferred from Binance.
- The existing Tabdeal trade-derived path is not silently promoted as the primary path by this adapter.

## Required next validation

Repeat the bounded BTCUSDT 15m Spot comparison through the new direct HTTP adapter, preserve raw-response SHA-256 values, and compare only fully closed candles. Keep Spot and USDⓈ-M Futures separate. Run the live public endpoint parity workflow and preserve its artifact hashes. Add Tabdeal or another broker only after its official public candle endpoint or documented SDK method is established; the currently reviewed official Tabdeal Postman collection did not expose a kline/candlestick request.

## Live parity workflow added

A bounded live public read-only workflow now captures both Binance Spot endpoint response hashes, compares at least eight common closed candles across timestamps/OHLC/volume/trade count, and uploads an evidence artifact on pass or failure. This is endpoint parity evidence only, not proof of website-chart backend identity or cross-venue parity.

## Native feature bridge

A dedicated adapter now converts validated native candles into the existing feature-engine candle contract while retaining source/product/digest metadata and enforcing historical as-of cutoffs. It does not silently substitute trade-derived pressure/VWAP when those inputs are unavailable. Strategy integration and broker-specific candle adapters remain separate validation work.

## Native OHLCV feature path

A native-only feature pipeline now creates the existing descriptive FeatureSnapshot from validated exchange candles. It uses native quote/base volume for window VWAP and native taker-buy volume for ratio/delta, preserving exact Decimal source data until the analytics boundary. Any observed gap or insufficient history blocks decision readiness. It does not invoke order execution.

## Same-batch feature journaling

The disabled-by-default forward runner now passes its single validated native batch through NativeOHLCVFeaturePipelineV1 and stores the resulting feature-quality/readiness state in the same immutable journal record. It never performs a second market-data fetch for features. A feature snapshot is withheld when readiness fails.

## Additional official USDⓈ-M historical raw-data path — 2026-10-17

A bounded read-only probe from the enrolled VPS downloaded Binance's official public USDⓈ-M daily kline archive for BTCUSDT 1m on 2026-10-16 from data.binance.vision. The ZIP response was HTTP 200, 60,989 bytes, and its SHA-256 matched the checksum published alongside the archive. The extracted CSV contained 1,440 rows with 12 fields per row and strictly increasing open times from 2026-10-16T00:00:00Z through 2026-10-16T23:59:00Z.

Evidence: evidence/native_ohlcv_usdm_official_archive_2026-10-16.json.

Important boundary: this proves an authorized route to official historical raw Futures archive bytes from this VPS; it does not prove live REST/WebSocket Futures connectivity. A direct request to https://fapi.binance.com/fapi/v1/klines timed out (HTTP 000). Do not route around that restriction. Keep the live Futures adapter unverified until an authorized direct live capture succeeds.

## Tabdeal candle endpoint status

The official Tabdeal Python SDK's Future client exposes ping, time, exchangeInfo, depth, and aggregate-depth methods in the reviewed public source; it does not expose a kline/candlestick method. A read-only probe of the previously considered /r/fapi/v1/klines path returned HTTP 404. This path is not accepted as an official candle endpoint. Continue to require a published official endpoint or a written response from Tabdeal support before implementing/promoting a Tabdeal native candle adapter.
