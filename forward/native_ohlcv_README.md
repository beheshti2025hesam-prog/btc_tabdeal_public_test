# Native Exchange OHLCV — v1

> **Canonical HES source decision (2026-10-30):** Gate.io Public Spot BTC_USDT persisted closed candles are the single source for HES chart and analysis. This document describes venue-specific adapters retained for parser/parity testing; the Binance adapters below are not the default Signal Agent source and must not be treated as the canonical HES market feed. Trade-derived candles are a secondary cross-check, not the source of truth.

## Legacy/test-only read-only venue adapters

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

## Adapter chart-parity protocol (not canonical-source qualification)

For a venue/product/symbol/interval, request the same bounded time window from the chart-optimized endpoint and its standard candle endpoint where available. Compare open_time, close_time, OHLC, and volume separately; record endpoint kind and raw-response hashes. Do not assume volume equality if the venue documents presentation-specific adjustments. Differences in OHLC are a blocker until explained. Futures are a separate product and must not be compared as though they were Spot.

## Extension boundary for other exchanges and brokers

Add one explicit adapter per official public candle endpoint or documented SDK. Keep venue, product, instrument, timeframe, timestamp convention, closure rule, and source digest in the record. Do not guess broker endpoints, reuse Binance rules for another venue, or silently fall back to trade aggregation.

A durable append-only one-shot collector is available in native_ohlcv_collector_v1.py. NativeOHLCVForwardRunnerV1 can also append a fully validated batch to the immutable forward observation journal in one record, without depending on trade.sequence. It is disabled by default and must be explicitly enabled for one bounded fetch. It is not a scheduled live collector or trading authorization.

## Historical Binance endpoint parity evidence

The `.github/workflows/native-ohlcv-live-parity-v1.yml` workflow performs a bounded, public, read-only comparison of BTCUSDT 15m Spot `uiKlines` and standard `klines`. It compares only closed candles, requires at least eight common closed candles, stores both exact raw-response SHA-256 values, and uploads a JSON artifact even when the probe fails. This establishes endpoint-to-endpoint parity for that sampled window only; it does not prove that the website's rendered chart uses either endpoint, nor does it validate other venues or brokers.

## Native candle feature boundary

Source-specific field availability is mandatory. Gate.io candle batches provide base/quote volume but do not provide trade count or taker-buy flow; those fields remain null/UNKNOWN and are never inferred from Binance or another venue.

`forward/native_ohlcv_feature_adapter_v1.py` is the explicit bridge from validated native OHLCV batches into the existing float-based core candle feature interface. Exact Decimal values and raw-response hashes remain in the source batch/journal; float conversion happens only at this analytics boundary. The envelope retains venue, product, timeframe, source digest, observation cutoff, and gap metadata. It does not silently create trade-side pressure or trade-derived VWAP features that are absent from a candle batch.

## Native feature pipeline

`NativeOHLCVFeaturePipelineV1` builds a descriptive `FeatureSnapshot` from native candles: EMA, a volume-weighted price computed as summed quote volume divided by summed base volume over the configured closed-candle window, taker-buy ratio/delta, volume, volatility/ATR, and regime. It preserves source digest and product identity. Any observed in-window candle gap blocks decision readiness; insufficient closed history and invalid quality also fail closed. This pipeline does not place orders.


## One-shot native feature journaling

When enabled explicitly, `NativeOHLCVForwardRunnerV1` now fetches one native batch, builds the feature snapshot from that same batch, and journals candles, source hash, feature-quality outcome, and the snapshot together. A snapshot is emitted only when feature quality, history sufficiency, and gap checks pass; otherwise the journal records the block reason and no usable snapshot. Execution remains OFF.
