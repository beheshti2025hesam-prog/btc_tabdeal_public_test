# Strategy Family Intelligence — Four-Family Research Protocol v1

**Date:** 2026-11-10  
**Scope:** Gate.io Public Spot BTC_USDT; closed 15m setup candles only.  
**Disposition:** research assessment only; no candidate authorization, confirmation, Risk approval, activation or execution.

## Non-negotiable boundaries

- Persisted global_market_data_reader_v1 rows remain the sole market-data input. This module performs no network I/O and does not create a second feed.
- 15m remains setup authority. 1m is downstream precision refinement only and is not read by this research assessor.
- Every assessment is bound to the exact bounded 15m row window with SHA-256 and the closed-candle observation timestamp.
- Existing Trend candidate path, Range evidence builder, structure engine, journal projection and learning loop are reused. No parallel strategy router, candle adapter, risk gate, trade journal or outcome ledger is created.
- Research eligibility is not a trade candidate and is not a performance outcome. Existing paper cohort/evaluation coordinator continues to recognize only its explicitly registered Trend Breakout and Range Mean Reversion profiles. New research IDs are not silently added to those cohorts.
- All outputs preserve candidate_generation_authorized=false, confirmation_approved=false, risk_approved=false, execution_enabled=false, orders_placed=false.

## Four independent research families

### 1. Trend Continuation

**Reuse:** existing OpportunityDetectorV1 candidate and causal structure events. The research family label maps to the current trend_breakout baseline candidate; it does not rename or replace the existing family profile.

Required observations:
- existing directional candidate is present;
- candidate direction matches current 15m structure regime (LONG/UPTREND or SHORT/DOWNTREND);
- latest directional BOS/CHOCH event agrees with candidate direction;
- MFI14 base-volume flow is directionally aligned (LONG >= 50; SHORT <= 50).

This is a research observation only. Existing Trend confirmation and shared Risk Gate remain independent and unchanged. The existing 5/6 StrategyPolicyV1 quorum is reused (the five mandatory checks must pass; MFI remains the optional sixth vote). Cost-adjusted geometry requires estimated net R >= 1.0 under the frozen simulation cost assumptions.

### 2. Breakout / Retest

Use the latest two closed 15m candles as breakout and retest, respectively. The 20 candles preceding the breakout candle define the prior range boundary. ATR is the arithmetic mean of the latest 14 true ranges from the bounded closed 15m window.

Required observations:
- breakout candle closes outside prior 20-bar high/low;
- retest candle closes back outside the same boundary in the breakout direction;
- retest wick reaches within 0.25 ATR of that boundary;
- MFI14 base-volume flow agrees with direction (LONG >= 50; SHORT <= 50);
- direction agrees with current trend regime, or classified regime is RANGE (where the breakout itself is the transition hypothesis).

The invalidation stop defines a gross 3R target; estimated net reward/risk after the explicit simulation fee/slippage assumptions must remain >= 1.0. No volume/trade-count/taker-buy fields are fabricated; Gate.io fields not present remain unavailable.

### 3. Range Reversion

**Reuse:** existing build_range_family_evidence and range_opportunity_policy_v1; do not duplicate calculations. Research display ID range_reversion is an alias for the existing range_mean_reversion research evidence builder, not a new paper-cohort identity.

Eligibility requires existing Range evidence builder to return READY with a direction and bound cost-model hash, and current regime to be RANGE. Existing independent eight-check research confirmation and common Risk Gate veto remain unchanged. Assumption-based costs do not satisfy verified-cost promotion gates. Research cost-adjusted geometry requires estimated net R >= 1.0.

### 4. Volatility Expansion

Use the same closed 15m OHLCV window:
- True Range and ATR14 are calculated causally.
- Bollinger width is 4 * population_std(close_20) / mean(close_20).
- Compression is present when median of the 20 width observations in the compression window is <= 75% of median of the preceding 20-observation baseline window.
- Expansion is present when current ATR14 is >= 1.25 times median of preceding rolling ATR14 observations AND current Bollinger width is >= 1.25 times median compression-window width.
- Direction is taken from latest directional BOS/CHOCH event only; historical opposing events cannot override latest event.
- MFI14 base-volume flow and regime/direction relationship must agree. The invalidation stop is the current closed candle extreme with a 0.1 ATR buffer; estimated net R after simulation fee/slippage must be >= 1.0.

The 0.75 and 1.25 compression/expansion multipliers and >=1.0 estimated net R geometry floor are preregistered research hypotheses, not tuned parameters or accepted profitability thresholds. They must be frozen before chronological validation; any later change requires a new protocol version and fresh holdout.

## Attribution and learning

- Canonical trade_journal_v2.jsonl stores the full assessment inside existing gate_evidence; trade_journal_view_v1 verifies family set, feature booleans, per-family evidence digests, source-window hash binding and all authority flags before projecting it.
- Existing dashboard journal row shows number of research-eligible families; its detail tooltip lists each family status and feature reasons.
- Existing read-only Learning Loop derives HYPOTHESIS_ONLY feature-failure counts from validated journal projections. It cannot edit policy or create candidates.
- NO_TRADE, missing evidence, unavailable data, and a research-eligible family are kept distinct. No synthetic outcome, inferred win, forced daily signal, or cross-family cohort pooling is permitted.

## Acceptance remains separate

- At least 100 eligible resolved outcomes per accepted family; strictly >90% win rate; positive net expectancy after costs; PF >1; verified fees/slippage; independent chronological OOS; clean provenance and family-specific linkage.
- Global daily actionable signal ceiling remains <=3, a ceiling not a quota.
- No family is activated by this research assessment or by a paper metric PASS alone.