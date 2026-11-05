# Gate.io Candle Decimal Equality — Design

## Intent
Allow the existing Gate.io REST collector to reconcile previously persisted candles when the exchange returns the same decimal values with different textual precision (for example, 312.074639 and 312.07463900).

## Goals
- Compare OHLCV and base/quote volume as exact decimal values, not string representations.
- Keep candle identity, timestamps, interval, and closed-state comparisons strict.
- Continue rejecting any genuinely different numeric value; no float conversion or tolerance.
- Leave existing live candle files, collectors, services, strategy policy, and execution state untouched by this code change.

## Non-goals
- No source-provider change: Gate.io Public Spot remains canonical.
- No candle backfill, rewriting, truncation, or normalization of existing live files as part of this fix.
- No strategy threshold, risk, signal, or execution changes.
- No automatic service restart or deployment.

## Approaches
1. Keep string equality: rejected because equivalent decimal values with different trailing zeros are incorrectly treated as conflicting market data.
2. Compare exact Decimal values: selected because it preserves exact numeric equality without floating-point rounding or tolerance and matches the collector's existing Decimal validation.
3. Compare floats or use a tolerance: rejected because it can mask real price/volume differences.

## Design
Update only _same_candle in forward/global_market_data_gateio_v1.py. Compare identity/timestamp/closed fields exactly; compare OHLCV and base/quote volumes using Decimal(str(value)), requiring finite values. Add regression tests proving formatting-only differences reconcile idempotently while real volume/quote-volume changes still fail closed.

## Acceptance
- Regression test fails on the current implementation for formatting-only differences.
- The regression passes after the minimal Decimal comparison change.
- Existing collector tests and the full repository suite pass.
- No live data file or service is changed; no live orders are possible or attempted.
