# HES Dashboard — Strategy Regime & Range Family

**Status:** documentation/design contract (2026-11-19). This document does not assert that a new dashboard panel has been implemented or deployed.

## Purpose and authority

The dashboard is an observation and control surface. It does not originate strategy decisions, bypass Mother Orchestrator, approve risk, or execute trades.

## Required fields

| Field | Display contract |
|---|---|
| Market regime | UPTREND, DOWNTREND, RANGE, TRANSITION or UNKNOWN; show timeframe and confidence/quality where available |
| Selected family | trend_breakout, range_mean_reversion, correction_pullback, breakout_transition or NONE |
| Family lifecycle | RESEARCH_ONLY, PAPER_SHADOW, ACCEPTANCE_PENDING, ACCEPTED or ACTIVE; show only evidence-backed state |
| Setup eligibility | Eligible / blocked / not evaluated with timestamp and deterministic reason codes |
| Range context | Validated support/resistance, width/persistence, price location and invalidation level, only when evidence exists |
| Confirmation | Independent confirmation/consensus state and requirement results |
| Risk Gate | Independent APPROVED / REJECTED / BLOCKED / NOT_EVALUATED state and reason |
| Trade geometry | Entry/stop/target, gross and net R, cost assumptions; distinguish estimates from verified costs |
| Data quality | Freshness, gaps, source, closed-candle status, session and provenance; stale/invalid warnings |
| Decision | TRADE_CANDIDATE / NO_TRADE / BLOCKED plus concise deterministic explanation |
| Execution boundary | execution_enabled and orders_placed remain visible; disabled means non-actionable |

## Range presentation rules

- Display Range as RESEARCH_ONLY / EDGE_NOT_PROVEN until formal acceptance.
- Never render research candidates as actionable signals, orders, or live strategy.
- LONG evidence requires a validated lower boundary plus reversal/structure confirmation; SHORT requires the symmetric upper-boundary evidence.
- Show range invalidation and routing to BREAKOUT/TRANSITION or NONE.
- Stale, incomplete, contradictory data; mixed/unknown regimes; costs erasing the edge; or a Risk Gate veto must display NO_TRADE/BLOCKED.
- Keep Trend's existing 3R contract distinct. Do not imply Range inherits its RR or that any research RR has been accepted.
- Corrections/pullbacks must not be labeled as stable ranges.

## Operator workflow

1. Check regime and data quality.
2. Check selected family and lifecycle; RESEARCH_ONLY means observe, not trade.
3. Inspect setup evidence and rejection reasons.
4. Inspect confirmation and independent Risk Gate outputs.
5. Review net-of-cost geometry and provenance.
6. Treat NO_TRADE as a valid final result. No dashboard control overrides a risk veto or execution approval process.

## Dashboard acceptance tests

- Correct rendering for all regime/family combinations, including UNKNOWN/NONE and transitions.
- Research-only Range is visibly non-actionable.
- LONG/SHORT evidence is symmetric.
- Router selection never appears as confirmation or risk approval.
- Stale/missing/contradictory data fails closed to NO_TRADE/BLOCKED.
- Verified and estimated costs are distinguished.
- Source, timestamp, freshness and provenance are visible.
- Trend behavior and existing security/localization contracts remain intact.
- No UI action directly creates, modifies or sends orders.

## Current status

Existing research records Range as RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN. The router maps RANGE to range_mean_reversion for research classification, but candidate generation is not authorized. No new dashboard panel, live signal route, production activation or execution permission is asserted. Implement only in a verified isolated worktree against the exact active source/release, with tests and explicit review.

## Related records

- Notion DNA & Roadmap: https://app.notion.com/p/41b0a937939181bcae32e628746b1324
- Notion Master Checkpoint: https://app.notion.com/p/3f80a937939181619f0fce6b19b968d0
- Existing research: docs/checkpoints/RANGE_STRATEGY_RESEARCH_AND_ROUTING_GAP_2026-11-04.md
- Router contract: docs/checkpoints/STRATEGY_FAMILY_ROUTER_CONTRACT_2026-11-04.md

## Current implementation/evidence update (2026-11-19)

The Range v2 engine exists in an isolated research branch and is not deployed or activated. Both the 90-day historical replay and recent VPS multi-timeframe shadow replay produced zero eligible candidates. Keep the dashboard status at RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN; do not display actionable Range signals. The engine binds to the shared family-context envelope but is not connected to Strategy V2 approval, Confirmation, Risk Gate, Precision Entry, order routing or live dashboard actions. Trend remains unchanged. See `docs/checkpoints/RANGE_STRATEGY_ENGINE_V2_RESULTS_2026-11-19.md`.
