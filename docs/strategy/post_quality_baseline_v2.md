# POST-QUALITY-BASELINE v2

## Why the legacy signal logic is rejected

The legacy baseline treated several correlated observations as independent
confirmations: close relative to EMA, close relative to VWAP, buy ratio,
trend bias and structure bias.

A 3-of-N score can therefore emit a signal without a verified structure event,
entry trigger, liquidity context or explicit risk/reward validation. EMA and
VWAP remain useful context features, but they are not independent proof of a
trade.

The old 1027/28 evaluation is historical and is not used as a target or
calibration set for this strategy.

## New decision model

A signal must pass all critical evidence families:

1. Data quality
2. HTF regime/trend alignment
3. Market-structure direction and confirmed break
4. Location/liquidity context
5. Entry trigger and displacement
6. Independent participation or momentum confirmation
7. No contradiction
8. Valid stop/invalidation
9. RR at or above the configured minimum, default 3.0

Failure or unknown state in any critical gate produces NO_TRADE.

## Indicator policy

EMA/EMA200/EMA50, VWAP, MFI, ADX/DI and volume remain useful, but their roles
are separated.

- EMA200/EMA50: trend and regime context, not a standalone entry trigger.
- VWAP: location/context, not a second independent vote against EMA.
- MFI/ADX/DI: momentum/regime evidence; correlated measurements are kept in
  one evidence family.
- Volume/participation: confirmation, not an unconditional entry trigger.
- OB/FVG/liquidity sweep: location and market-structure context.
- Candle/displacement/reclaim: actual entry trigger.
- SL/invalidation and RR: mandatory risk gate.

No fixed indicator threshold is promoted to truth merely because it worked in
the historical baseline. Thresholds must earn promotion through walk-forward
and OOS evidence.

## Direction

Long and short use the same gate architecture. Direction is never inferred
from a majority vote between correlated indicators.

## Promotion

This branch defines a new operational baseline. It must earn promotion through
a fresh OOS/walk-forward evaluation with immutable inputs and explicit
candidate -> eligible -> signal -> outcome lineage.

No historical record is deleted or reclassified.
