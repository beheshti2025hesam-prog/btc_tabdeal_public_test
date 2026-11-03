# HES 1m Precision Paper Journal — Acceptance Contract

**Status:** candidate implementation; paper-only; not deployed.
**Market data:** Gate.io Public Spot `BTC_USDT` only.
**Authority:** 15m Strategy Policy V2 owns setup direction and approval. The 1m engine is advisory entry timing only.

## Immutable artifacts

The journal writes three independent JSONL streams beneath the shared mutable data root:

- `precision_entry_events_v1.jsonl`: one deterministic setup + closed-candle observation.
- `precision_entry_candidates_v1.jsonl`: at most one paper candidate per validated 15m setup.
- `precision_entry_outcomes_v1.jsonl`: a separate immutable outcome event; the original candidate is never edited.

A repeated event ID with identical content is an idempotent replay. Reuse of an event ID with different content is an integrity conflict and must fail closed. A maximum of three paper candidates per UTC day is a cap, never a quota.

## Outcome rules

- Resolve only from canonical, closed, contiguous Gate.io 1m candles after the candidate entry close.
- Stop and target touched in the same 1m candle is conservatively scored as a loss.
- A 24-hour holding horizon ends at the first closed candle reaching the deadline; no later candle can retroactively improve the result.
- A gap, missing candle, invalid bar, or unavailable history leaves the candidate unresolved. Never interpolate or infer the missing price path.
- Gross R is not net performance. Fees/slippage remain `ASSUMPTION_BASED_NOT_VERIFIED` until verified.
- A candidate older than the retained history is reported as outside the resolution window; it is not assigned a synthetic win/loss/timeout.

## Retention and recovery

Gate.io Spot candlestick REST accepts at most 1,000 rows per request. The 1m collector therefore fetches a newest 1,000-row page plus the immediately preceding 500-row page, validates the combined contiguous sequence, and persists a rolling 1,500 closed-candle window. This covers one 24-hour outcome horizon plus a one-hour recovery margin. Existing 15m, 1h and 4h retention remains 500 candles.

A downtime longer than the recovery margin can leave older candidates unresolved. The report exposes this as `PARTIAL_HISTORY_UNAVAILABLE`; it must not silently claim a complete cohort. Longer outage recovery would require a separately tested, candidate-scoped historical backfill.

## Release and state boundary

- Code runs only from `/opt/hes-trade-agent/current`.
- Mutable journals/reports live only beneath `HES_DATA_ROOT=/opt/hes-trade-agent/data/forward`.
- systemd grants write access only to the shared data and log paths.
- The unit is a template only; it must not be installed or started until release, VPS backup, service allow-list, and explicit change-window checks are complete.
- This journal never calls an exchange execution API. `execution_enabled=false` and `orders_placed=false` are invariants.

## Required CI evidence

1. Full repository regression with warnings treated as errors (`bash scripts/run_regression_suite.sh`).
2. Dashboard single-path API contract.
3. Browser render proving 15m/1m chart data matches the same API reader batch.
4. Focused tests for 24-hour timeout, stop/target ambiguity, gaps, 1,500-bar retention/pagination, immutable event conflict, and release/data-root separation.

## Performance reporting

Only resolved, preapproval-paper-eligible candidates belong in the resolved win-rate denominator; unresolved candidates and timeouts must be separately reported, and timeout inclusion/exclusion must be explicit. Report LONG/SHORT and regime splits, costs, expectancy, profit factor, drawdown and independent forward results. Do not claim a >90% win rate until the project acceptance sample floor and independent out-of-sample requirements are met.
