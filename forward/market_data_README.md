# Market Data → Normalized Candle Layer v1

This layer converts fresh Tabdeal trade observations into deterministic 15m candle inputs.

## Boundary

Raw trades → deterministic 15m candles → downstream feature/structure layers.

It does **not** contain:
- indicators
- thresholds
- signal rules
- risk rules
- outcomes
- historical Winner/Survivor logic

## Integrity rules

- Source sequence identity is preserved.
- Duplicate sequences are rejected when conflicting and ignored when identical.
- Timestamps must be timezone-aware.
- Closed-candle construction must only use observations available by the candle close.
- Missing intervals are never silently fabricated.
- Price and volume retain source numeric precision.

## Important

The current implementation is a normalization contract/reference implementation. It is not yet wired into the live collector and therefore does not change collection behavior.

## Separate venue-native OHLCV path (research / adapter only)

The Tabdeal trade-to-candle contract above remains unchanged and is not a native candle client. A separate read-only Wallex native OHLCV adapter is documented in `forward/wallex_native_candles_README.md`. It is isolated and **not wired into the collector or decision path**. Its bounded live REST and WebSocket smoke records are under `evidence/`; these records do not prove chart parity, national-intranet compatibility, or trade identity/order/replay semantics.
