# Market Structure Layer v1

Forward-only structure measurement boundary.

## Purpose
Translate normalized 15m candles into auditable structure state.

Supported vocabulary:
- Swing High / Swing Low
- HH / HL / LH / LL
- BOS / CHOCH
- UPTREND / DOWNTREND / RANGE / UNKNOWN

## Safety
This layer does not produce LONG/SHORT decisions and does not optimize against outcomes.
No historical Winner/Survivor population is consumed.

## Important implementation note
The current module is a measurement primitive/reference contract. Swing confirmation and BOS/CHOCH policies must be introduced as explicitly versioned policies; no hidden look-ahead is permitted.
