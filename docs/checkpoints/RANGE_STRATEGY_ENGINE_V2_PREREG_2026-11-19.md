# HES Range Strategy Engine v2 — Preregistration

**Date:** 2026-11-19
**Status:** RESEARCH ONLY / NOT ACTIVE / NO PAPER ELIGIBILITY / NO DEPLOYMENT
**Base release:** 09f660d625df3f8964ba8ddd20c9a9cf8a400f19
**Router/context contract:** router v1.1.0 / family context v1.1.0
**Market:** Gate.io Public Spot BTC_USDT; 15m setup; 1m remains downstream-only.

## Hypothesis

A persistent, two-sided BTC 15m range may produce a mean-reversion opportunity when price sweeps a statistically defined prior boundary and closes back inside with wick rejection and RSI/MFI reversal. This hypothesis is not assumed profitable.

## Frozen v2 policy

- Prior-only 64-bar boundary window; lower 10th percentile of lows and upper 90th percentile of highs; signal candle excluded.
- Require at least two touches on each boundary, with 12 or more bars between first and last touch on each side.
- At least 80% of prior closes remain within the boundary envelope plus/minus 0.25 ATR.
- Range width 3–14 ATR; CHOP(14) >=58; ER(20) <=0.25; ADX(14) below 23 on 15m and below 28 on 1h/4h; normalized EMA50 slope on 1h/4h <=0.60 ATR over four bars.
- Entry hypothesis: completed 15m wick sweep/reclaim; wick/body >=1.25; close within 30% of the relevant boundary; RSI reversal (<45 rising for LONG, >55 falling for SHORT); MFI directionally confirms.
- Stop beyond signal wick by 0.15 ATR; first target is range midpoint.
- Cost model is mandatory and explicitly identified. Net-RR estimate subtracts round-trip cost from reward and adds it to risk. Research floor 1.20 net R; not an approved risk threshold.
- All candidates remain research-only. No confirmation, risk approval, candidate-generation authority, execution or orders are enabled.

## Validation protocol

- Use closed, strictly contiguous candles only; require 220 bars per timeframe and reject gaps, future bars, stale or missing volume fields.
- 15m setup is causal and bound to its close. 1h/4h context must also be fully closed at that time.
- Backtest entry at the next contiguous 15m open, not the signal close. Stop is resolved before target if both touch in one candle. Missing next candle or gaps invalidate the observation.
- Report 5/10/15/30 bp round-trip cost scenarios as assumptions unless verified venue-specific fills/fees are supplied.
- Freeze this policy before looking at outcomes. No same-sample threshold changes. Use chronological train/holdout and independent OOS evidence.
- Require at least 100 resolved eligible trades, strict project paper-quality target (>90% win rate), positive net expectancy after verified costs, acceptable drawdown/tail risk, and walk-forward/OOS stability before acceptance review. These are gates, not guarantees or quotas.

## Known constraints

The previous sweep/reclaim and Bollinger v1.x prototypes failed to establish an edge; the Bollinger sample was negative under all tested assumed costs. This v2 policy is a new preregistered hypothesis, not a relabeling or activation of those policies. A 90-day 15m sample does not supply a 90-day 1m precision-entry sample.

## Authority boundary

The module emits research observations only and binds candidate evidence into the shared provenance-bound strategy-family context envelope. It is not wired to Strategy V2 candidate approval, Confirmation/Consensus, Risk Gate, Precision Entry, order routing or live dashboard actions. Trend profile and its 3R contract remain unchanged. Unknown/mixed regimes continue to fail closed to NO_TRADE.
