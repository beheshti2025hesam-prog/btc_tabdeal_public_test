# HES Trade Agent — Strategy Family Intelligence Architecture

**Decision date:** 2026-11-10  
**Status:** APPROVED DIRECTION / RESEARCH-ONLY / NO LIVE ACTIVATION  
**Base:** PR #480 head 1f81f90897441c3501c802416ed300c4725de2d2

## Problem statement

The current production-facing opportunity policy is a narrow conjunctive breakout baseline. Existing family routing is a fail-closed identification contract, not an authorized research candidate generator. Range prototypes have not demonstrated an edge: sweep/reclaim produced no candidates in the frozen historical sample, and the Bollinger prototype's eight proxy outcomes were all losses under assumed costs. The system must not solve low signal frequency by relaxing global gates or counting rejected proposals as trades.

## Target family portfolio

| Family | Research setup | Initial regime/context | Lifecycle |
|---|---|---|---|
| Trend Continuation | validated trend + pullback + continuation structure | UPTREND / DOWNTREND | RESEARCH_ONLY |
| Breakout / Retest | closed-bar boundary break, acceptance, retest and hold | range escape / transition / directional | RESEARCH_ONLY |
| Range Reversion | persistent range, boundary extreme, sweep/reclaim/reversal | RANGE only | RESEARCH_ONLY |
| Volatility Expansion | compression followed by confirmed expansion and directional structure | compression-to-expansion transition | RESEARCH_ONLY |

The existing trend_breakout v2 baseline remains frozen and must be replay-equivalent. It is not silently renamed, replaced or loosened. Existing range_mean_reversion research evidence is retained; no old negative holdout is reused for tuning.

## Authority chain

1. Gate.io Public Spot BTC_USDT is the sole canonical source for market data, candles, charts and indicators.
2. Closed 15m candles own setup detection and regime authority.
3. The Mother Strategy Orchestrator dispatches independent family evaluators using validated, time-aligned context. A family may be eligible for research evaluation; this is not a candidate, confirmation, risk or execution approval.
4. Each family binds candidate identity, family ID/version, setup timestamp, direction, regime, feature evidence, source hashes, policy hash and cost-model version.
5. Shared confirmation consumes the same immutable family-bound context.
6. Existing 1m precision entry refines an already valid 15m setup. It cannot create an independent setup.
7. Independent Risk Gate may veto every family. No family-specific logic can weaken or bypass it.
8. Paper evaluator, decision journal, outcome resolver and learning loop record proposals, rejections, missed opportunities and resolved outcomes separately, with independent family cohorts.
9. Promotion requires frozen policy, exact cost evidence, chronological walk-forward and independent holdout, risk approval, review, immutable release and explicit authorization.

## Research dispatch contract

The orchestrator may return zero, one or multiple research_eligible_families after validating explicit closed-candle feature evidence. It must return zero on missing, stale, malformed, conflicting, non-finite or unbound evidence. Eligibility never authorizes signal generation or orders. Family-specific evaluators decide whether an actual setup exists and must write proposals to research-only ledgers. No synthetic or retroactive trade attribution is allowed.

### Minimum evidence per family

- Trend Continuation: HTF direction/persistence, pullback location, continuation BOS/CHOCH or equivalent structure, directional flow, valid stop and cost-adjusted target geometry.
- Breakout / Retest: prior boundary provenance, closed-bar break, acceptance outside boundary, retest, hold/reclaim evidence, volume/flow and invalidation.
- Range Reversion: persistent range classification, boundary-only location, liquidity sweep/reclaim, reversal structure and cost-adjusted geometry. No mid-range fading.
- Volatility Expansion: prior compression state, measured volatility expansion, confirmed directional displacement, structure/flow confirmation, false-break invalidation and cost-adjusted geometry.

These are research contract requirements, not validated thresholds. Thresholds must be preregistered from training data and frozen before validation/holdout.

## Evidence ladder and no-deadlock rule

- No 1,000-trade prerequisite. The current project minimum for an acceptance claim is at least 100 eligible resolved trades per family, but 100 is a floor, not proof by itself. Always report confidence intervals and uncertainty.
- Stage gates: deterministic tests -> historical exploratory diagnostics -> preregistered chronological train/validation/holdout -> forward-only paper cohort -> independent review/promotion.
- Small samples may reject a hypothesis or produce descriptive results; they cannot establish profitability.
- No loosening filters just to increase count, no pooling across families, no counting rejected/NO_TRADE proposals as trades, and no tuning against final holdout.
- Three actionable signals per UTC day is a global ceiling, never a quota. NO_TRADE remains valid whenever any integrity, setup, cost, confirmation or risk gate fails.

## Acceptance per family

The aspiration remains strictly greater than 90% paper win rate over at least 100 eligible resolved trades. Also required: verified fees/spread/slippage for the actual execution product (plus funding/borrow when applicable), positive net expectancy, PF > 1, controlled drawdown/tail loss, independent chronological OOS/walk-forward evidence, valid provenance and Risk approval. Report gross/net win rate, CI, sample count, net expectancy, PF, max drawdown, cost sensitivity, exposure and rejection/missed-opportunity attribution. No guarantee is made that every family can attain the target.

## Non-goals / safety invariants

- No live order, account connection, leverage change, production policy mutation or activation in this work.
- execution_enabled=false; orders_placed=false; family_live_activation=false; risk_gate_bypass=false.
- No duplicate market-data collector, journal, router, generic execution engine or VPS.
- Do not modify the dirty primary checkout or active immutable release.
- Keep Mother Agent chat/Command Center on free capabilities.
- Preserve encrypted Dropbox backup/restore as a separate release gate.

## Delivery sequencing

Protect 2026-11-19 delivery. First deliver auditable family identification, research eligibility and journal/learning observability with no live authority. Keep any unproven family in research-only state. A safe, usable app that reports insufficient evidence is preferable to a premature strategy activation.