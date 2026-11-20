# HES Range Strategy Engine v2 — Research Results

**Date:** 2026-11-19
**Status:** RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN / NO DEPLOYMENT
**Branch:** feat/range-strategy-research-v1-20261119
**Base release:** 09f660d625df3f8964ba8ddd20c9a9cf8a400f19
**Router:** hes-strategy-family-router-v1.1.0

## Implementation

- Added a standalone, versioned Range mean-reversion research engine (forward/range_strategy_engine_v2.py) and frozen policy contract (forward/range_strategy_engine_v2.json).
- Uses prior-only 64-bar dynamic boundaries, two-sided touch/persistence tests, CHOP/ER/ADX regime filters, 1h/4h EMA50 pressure checks, closed-candle sweep/reclaim, RSI/MFI reversal, wick validation and cost-adjusted midpoint geometry.
- Added an adapter into the existing provenance-bound strategy-family context envelope. Range profile version is now hes-range-mean-reversion-v2.0.0-research; router/context contract versions are bumped. All authority fields remain false.
- Existing Trend profile and its 3R minimum/gates are unchanged. The engine is not connected to Strategy V2 candidate approval, Confirmation, Risk Gate, Precision Entry, order routing or live dashboard actions.

## 90-day historical replay

- Source: 8,639 closed Gate.io Spot BTC_USDT 15m candles, 2026-08-06T19:45:00+00:00 through 2026-11-04T19:30:00+00:00.
- Source gap count: 0; source SHA-256: b1b411118bdb103491a4c9a713a63367fbe1cb985e8d5bf26eb50168d7e5f1c1.
- HTF context was causally resampled from the same 15m source into 2,159 1h and 539 4h candles aligned to UTC boundaries; it is not an independent feed.
- First evaluated setup: 2026-09-12T13:15:00+00:00.
- Prior-boundary sweep/reclaim prefilter bars: 646.
- Final candidate signals: **0**. No trades were opened in the simulation.
- Rejection reasons:
  - BOUNDARY_TOUCHES_NOT_PERSISTENT: 223
  - NO_UNAMBIGUOUS_SWEEP_RECLAIM_REVERSAL: 16
  - RANGE_CLASSIFIER_NOT_CONFIRMED: 322
  - RANGE_WIDTH_OUT_OF_BOUNDS: 41
  - TREND_STRENGTH_TOO_HIGH: 44

| Assumed round-trip cost | Eligible candidates | Resolved trades | Win rate | Net expectancy |
|---:|---:|---:|---:|---:|
| 5 bp | 0 | 0 | N/A | N/A |
| 10 bp | 0 | 0 | N/A | N/A |
| 15 bp | 0 | 0 | N/A | N/A |
| 30 bp | 0 | 0 | N/A | N/A |

No win rate, expectancy or profitability conclusion can be drawn from zero trades. The result is not a 0% win rate.

## Recent VPS forward-candle shadow replay

- Actual 15m source: 1,733 closed candles, 2026-11-01T06:00:00+00:00 to 2026-11-19T07:15:00+00:00.
- Actual 1h source: 1,119 closed candles, 2026-10-03T16:00:00+00:00 to 2026-11-19T07:00:00+00:00.
- Actual 4h source: 654 closed candles, 2026-08-02T04:00:00+00:00 to 2026-11-19T04:00:00+00:00.
- Actual 1m source: 19,985 closed candles, 2026-11-05T10:10:00+00:00 to 2026-11-19T07:15:00+00:00. All four files passed strict monotonicity, uniqueness and contiguous-cadence checks.
- The 1h and 4h context uses actual Gate.io candle files, not resampled 15m data.
- Final Range research candidates: **0**.
- Rejection reasons:
  - BOUNDARY_TOUCHES_NOT_PERSISTENT: 538
  - NO_UNAMBIGUOUS_SWEEP_RECLAIM_REVERSAL: 1
  - RANGE_CLASSIFIER_NOT_CONFIRMED: 769
  - RANGE_WIDTH_OUT_OF_BOUNDS: 75
  - TREND_STRENGTH_TOO_HIGH: 131

| Assumed round-trip cost | Raw candidates | Cost-pass | Complete 1m window |
|---:|---:|---:|---:|
| 5 bp | 0 | 0 | 0 |
| 10 bp | 0 | 0 | 0 |
| 15 bp | 0 | 0 | 0 |
| 30 bp | 0 | 0 | 0 |

Because no candidate survived the setup filters, no 1m precision-entry decision was attempted. A complete 1m data window would only prove data availability, not a READY entry.

## Interpretation and decision

- The v2 frozen hypothesis did not produce any eligible candidates in either the 90-day historical replay or the recent VPS forward-candle replay.
- This is evidence of insufficient candidate frequency under the frozen contract, not evidence that all range strategies fail and not a measured win rate.
- Do not loosen thresholds on either of these same samples. Any alternative hypothesis requires a separately versioned preregistration and untouched future/holdout data.
- Keep Range at RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN; current routing remains family identification only. Continue fail-closed NO_TRADE when no approved family setup exists.
- The project target of at least 100 resolved eligible trades, strict >90% paper-quality target, positive net expectancy after verified costs, acceptable drawdown and independent OOS remains unmet.
- No live service, release pointer, execution setting, account connection or order was changed.

## Validation

- Focused Range/family/router/context/journal tests: 61 passed.
- Full repository regression after final router/context/policy integration: 1,610 passed, 84 subtests passed.
- git diff --check and UTC-aligned HTF resampling checks passed before final integration.

## Next safe step

Collect additional forward-only observations and resolve the range/transition classification gap. Do not activate the module or force a daily trade quota. A separately preregistered next hypothesis may be considered only on untouched future data; no same-sample retuning is permitted.
