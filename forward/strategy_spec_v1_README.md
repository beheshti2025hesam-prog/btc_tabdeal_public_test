# Forward Strategy Specification v1

This is the first clean-room strategy specification boundary.

It deliberately defines **what must be explicit**, not invented thresholds.

## Non-negotiable rules

1. No historical Winner/Survivor data.
2. No historical performance tuning.
3. No future-outcome leakage.
4. LONG and SHORT must be symmetric where the market logic permits.
5. UNKNOWN or missing required evidence fails closed to NO_TRADE.
6. Win-rate targets are not optimization parameters.
7. Live execution remains disabled.

The specification is **DRAFT_NOT_ACTIVE** until every required rule is
explicitly defined, versioned, reviewed, and validated against fresh forward
observations.

The first forward period is an evaluation period, not a tuning loop.
