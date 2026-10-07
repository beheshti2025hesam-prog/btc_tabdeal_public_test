# Structure Policy Implementation v1

Implements the explicit two-left/two-right confirmed swing rule.

A pivot is never emitted until the two right-side 15m candles have closed.
Missing 15m intervals prevent confirmation across the gap.

The pivot timestamp remains the pivot candle close; the caller's observed_at
is the actual availability point.

This implementation is observation-only and does not generate trades.
