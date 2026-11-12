# HES Native OHLCV Indicator Snapshot v1

## Purpose

Expose the existing descriptive feature pipeline in the existing dashboard. This is a projection of the same validated, persisted Gate.io Public Spot candle batch already used by the chart and analysis path. It is not a second market-data request, a new calculator, a strategy, or a signal authority.

## Identity and provenance

Every response uses schema `hes_native_ohlcv_indicator_snapshot_v1` and carries:

- `source=gateio_public_spot`, `source_reader=global_market_data_reader_v1`, venue `gateio`, product `spot`.
- The requested internal symbol and timeframe.
- `input_batch_sha256` from the exact candle batch served to the chart.
- `feature_batch_sha256` from the existing feature pipeline.

The UI displays values only when both hashes match, the feature pipeline reports `decision_ready=true`, the quality gate passes, and execution flags are both false. A mismatch or missing value is rendered as blocked/unknown; stale or alternate values are never substituted.

## Descriptive fields

- EMA with the configured existing EMA period (currently 20).
- VWAP with the configured existing VWAP period (currently 20).
- Average True Range.
- Realized volatility.
- Volume ratio.
- Market regime label.

These values are calculated by the existing `NativeOHLCVFeaturePipelineV1` from Gate.io candles. No additional indicator implementation or external data provider is introduced.

## Safety boundary

The snapshot is descriptive only. It cannot create, rank, confirm, or authorize a trade; it cannot alter the 15m setup gate or 1m Precision Entry role; it cannot write journals or submit orders. The response always states `execution_enabled=false` and `orders_placed=false`.

If the feature quality gate or batch-provenance check fails, all indicator values are null and `status=BLOCKED`. This API projection does not relax any upstream freshness, candle-gap, volume-semantics, or risk policy.

## Compatibility

The schema is versioned independently from the strategy and journal contracts. Consumers must ignore unknown future fields and must not infer trade authority from `status=READY`; it means only that the descriptive snapshot passed its data/quality/provenance gates.
