# Range & Correction Strategy Architecture Decision — 2026-11-19

## Decision

Adopt modular multi-regime strategy coverage. Add Range as a dedicated specialist family inside the existing HES architecture, not as a parallel trading stack. Keep Trend unchanged. Treat Correction/Pullback and Breakout/Transition as separate family paths; UNKNOWN/mixed/low-quality regimes route to NO_TRADE.

## Reuse boundary

Reuse canonical Gate.io readers, 15m setup authority, 1m precision refinement, Market Regime Engine, strategy-family router/context, Confirmation/Consensus, Risk Gate, journal, Blackbox and Learning Loop. No duplicate collector, router, precision engine, journal or risk engine.

## Range contract requirements

- LONG near a validated lower boundary and SHORT near a validated upper boundary, both requiring reversal/structure confirmation.
- Boundary quality, width/persistence, range invalidation, data freshness, cost-adjusted geometry and independent risk approval are mandatory.
- Candidate evidence may include support/resistance, ADX/CHOP/ER, RSI/MFI, Bollinger, VWAP, volume, liquidity sweeps, BOS/CHOCH, Order Blocks and FVG. No indicator alone triggers a trade.
- Confirmation and Risk Gate remain independent, fail-closed gates. Trend's existing contract is behaviorally unchanged.

## Acceptance gates

Preregistered research; at least 100 resolved eligible observations; project strict >90% paper win-rate target; positive net expectancy after verified fees/spread/slippage/funding where relevant; acceptable drawdown/tail risk; chronological walk-forward and independent OOS. These are gates, not guarantees or frequency quotas. NO_TRADE remains valid. Live execution remains separately gated by explicit human approval.

## Evidence/status

Prior research: RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN; earlier prototypes did not establish positive net edge and transaction costs materially affected results. The existing router classifies RANGE as range_mean_reversion for research only; candidate generation remains unauthorized. This checkpoint records architecture and documentation, not a completed implementation, activation or deployment.

## Dashboard contract

See docs/dashboard/STRATEGY_REGIME_AND_RANGE_FAMILY_V1.md. Show regime, selected family/lifecycle, setup/rejection reasons, confirmation, independent Risk Gate, net-of-cost geometry, freshness/provenance and execution-disabled state. Research-only candidates must never appear actionable.

## Engineering follow-up

Verify exact active release and isolated worktree, inventory existing code and implement only proven gaps. Preserve the dirty main checkout and all untracked files. No reset/clean, production pointer change, service restart, merge, deployment, strategy/risk mutation or order action is authorized by this documentation update.

Dashboard Notion page: https://app.notion.com/p/41d0a9379391811b9001d44da9393bb7

## Engine v2 implementation/evidence update (2026-11-19)

- Isolated implementation branch: `feat/range-strategy-research-v1-20261119`, based on active release `09f660d625df3f8964ba8ddd20c9a9cf8a400f19`.
- Range family profile updated to v2 research; shared router/context contracts versioned forward; Trend unchanged.
- Historical and recent VPS shadow replays both produced zero eligible candidates. No performance/edge conclusion can be drawn; no same-sample tuning is allowed.
- Full repository regression: 1,610 passed, 84 subtests passed. No deployment, live activation, execution or orders.
- Detailed evidence: `docs/checkpoints/RANGE_STRATEGY_ENGINE_V2_RESULTS_2026-11-19.md` in the implementation branch.
