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
