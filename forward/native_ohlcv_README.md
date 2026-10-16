# Native Exchange OHLCV — v1

**Primary path:** venue-provided OHLCV candles. Trade-derived candles are a secondary cross-check, not the source of truth.

## Implemented read-only sources

- Binance Spot chart-optimized uiKlines (/api/v3/uiKlines) via the official public market-data-only host data-api.binance.vision
- Binance Spot standard klines (/api/v3/klines) for parity checks via data-api.binance.vision
- Binance USDⓈ-M Futures klines (/fapi/v1/klines)

All requests are public HTTPS GETs. No API keys, private account endpoints, orders, or trading calls are present. The default timeout is 10 seconds. No network call occurs merely by importing a module or constructing a source; fetch() explicitly performs the read.

## Safety and integrity

- Decimal precision is preserved with Decimal; timestamps remain source epoch milliseconds.
- Only closed candles are returned. An unfinished/current candle is excluded.
- Exact duplicate open times are idempotent; conflicting duplicates are rejected.
- Missing intervals are reported only between observed candles. No synthetic candle is created, and no leading/trailing gap is inferred without a bounded request window.
- Exact raw response bytes are SHA-256 hashed.
- Fixed-duration intervals are supported. Weekly/monthly calendar intervals remain disabled pending explicit alignment rules.
- Malformed wire types, timestamps, OHLC, volume, and endpoint responses fail closed.

## Chart parity protocol

For a venue/product/symbol/interval, request the same bounded time window from the chart-optimized endpoint and its standard candle endpoint where available. Compare open_time, close_time, OHLC, and volume separately; record endpoint kind and raw-response hashes. Do not assume volume equality if the venue documents presentation-specific adjustments. Differences in OHLC are a blocker until explained. Futures are a separate product and must not be compared as though they were Spot.

## Extension to other exchanges and brokers

Add one explicit adapter per official public candle endpoint or documented SDK. Keep venue, product, instrument, timeframe, timestamp convention, closure rule, and source digest in the record. Do not guess broker endpoints, reuse Binance rules for another venue, or silently fall back to trade aggregation.

A durable append-only one-shot collector is available in native_ohlcv_collector_v1.py. NativeOHLCVForwardRunnerV1 can also append a fully validated batch to the immutable forward observation journal in one record, without depending on trade.sequence. It is disabled by default and must be explicitly enabled for one bounded fetch. It is not a scheduled live collector or trading authorization.

## Live endpoint parity evidence

The `.github/workflows/native-ohlcv-live-parity-v1.yml` workflow performs a bounded, public, read-only comparison of BTCUSDT 15m Spot `uiKlines` and standard `klines`. It compares only closed candles, requires at least eight common closed candles, stores both exact raw-response SHA-256 values, and uploads a JSON artifact even when the probe fails. This establishes endpoint-to-endpoint parity for that sampled window only; it does not prove that the website's rendered chart uses either endpoint, nor does it validate other venues or brokers.

## Native candle feature boundary

`forward/native_ohlcv_feature_adapter_v1.py` is the explicit bridge from validated native OHLCV batches into the existing float-based core candle feature interface. Exact Decimal values and raw-response hashes remain in the source batch/journal; float conversion happens only at this analytics boundary. The envelope retains venue, product, timeframe, source digest, observation cutoff, and gap metadata. It does not silently create trade-side pressure or trade-derived VWAP features that are absent from a candle batch.
