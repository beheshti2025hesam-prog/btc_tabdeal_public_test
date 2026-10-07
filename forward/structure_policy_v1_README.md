# Structure Policy v1

Explicit forward-only structural policy for observation.

## Pivot confirmation
A 15m candle becomes a confirmed swing only after two candles on each side
are closed. The pivot is therefore attributed to the pivot candle but is only
observable at the close of the second right-side confirmation candle.

Strict comparison is required; equal extremes are not swings.

## Why this is not look-ahead
The right-side candles are not used before they exist. They delay confirmation
of the pivot instead of rewriting an earlier observation.

## Boundary
This policy is structural measurement only. It does not define entry,
confirmation confluence, risk, position sizing, RR, profitability, or execution.
Historical Winner/Survivor populations and future outcomes are forbidden.

Status: ACTIVE_OBSERVATION_ONLY.
