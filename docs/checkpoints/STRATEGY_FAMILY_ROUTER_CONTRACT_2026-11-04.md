# HES Trade Agent — Strategy Family Router Contract

**Date:** 2026-11-04  
**Version:** `hes-strategy-family-router-v1.0.0`  
**Disposition:** FOUNDATION ONLY / NOT WIRED INTO ACTIVE DECISION PIPELINE / NO STRATEGY ACTIVATION.

## Why this step

The 2026-11-04 strategy diagnosis found that the active opportunity policy rejects non-directional regimes, while the existing Strategy V2 is a conjunctive trend-breakout candidate. The two range prototypes remain research-only and did not establish a positive edge. A second independent audit found that downstream entry context and precision-entry contracts assume directional regimes and a 3R minimum.

The correct next step is a shared, versioned family-routing contract—not another indicator, not loosening the trend policy, and not activating an unprofitable range prototype.

## What was added

- `forward/strategy_family_router_v1.py`: immutable family profiles and fail-closed regime routing.
- `tests/strategy/test_strategy_family_router_v1.py`: deterministic invariants for scope, routing, immutability, and execution boundaries.

## Routing contract

| 15m regime | Family | Lifecycle | Candidate generation |
|---|---|---|---|
| UPTREND | trend_breakout | CANDIDATE_LOCKED_NOT_ACTIVE | Not authorized |
| DOWNTREND | trend_breakout | CANDIDATE_LOCKED_NOT_ACTIVE | Not authorized |
| RANGE | range_mean_reversion | RESEARCH_ONLY_NOT_ACTIVE | Not authorized |
| Other / unknown | none | NO_FAMILY | Not authorized |

## Preserved boundaries

- Gate.io Public Spot BTC_USDT remains the sole canonical source for live market data, candles, charts, and indicators.
- 15m remains the setup-authority timeframe; 1m is precision-entry refinement only and cannot originate a setup.
- Existing Strategy V2 breakout rules and 3R geometry are unchanged.
- The range profile has no approved RR threshold and makes no profitability claim.
- Both family profiles are immutable and have signal generation, execution, and order placement disabled.
- Confirmation, risk, final policy approval, and execution remain separate gates. Routing never implies their approval.
- No API credentials, private exchange calls, orders, leverage changes, service restarts, deployment, or active-policy changes were performed.

## Acceptance still required before wiring

1. Define a common family-aware setup/context schema with explicit family ID, version, regime, and provenance.
2. Make confirmation and risk policies consume family-specific requirements without weakening the shared fail-closed veto.
3. Keep the trend profile byte-for-byte behaviorally equivalent under replay tests.
4. Validate any range family on preregistered chronological training/holdout data with independently verified costs, sufficient resolved trades, and positive net expectancy/PF/drawdown criteria.
5. Add family attribution to the journal and rejection/loser evaluation.
6. Wire the router only after all above tests pass; keep execution disabled until separately authorized.

## Verification

- Focused router tests: **12 passed** with warnings treated as errors.
- Full repository regression: **666 passed in 4.97s**, warnings treated as errors.
- `git diff --check`: passed.
- SHA-256 `forward/strategy_family_router_v1.py`: `926a2d0f54a6875fa057c6f1df0bd6605b6900b51bedccd7bb5589e68954031f`.
- SHA-256 `tests/strategy/test_strategy_family_router_v1.py`: `cca75b32e51ca040f8926f722b9896e929f43dfb90ebee2e930a034cf550505b`.
- SHA-256 this checkpoint: `069941f6ba3857385bdc78f4d29e897e1dae5d405f8c3bda656a71cabd88890f` (before this verification text update).
- No runtime behavior, active strategy, release pointer, service, or execution setting changed. The new router is deliberately not wired into the live decision pipeline.


## 2026-11-05 — Family context integrity and journal attribution

- Added a provenance-bound family context envelope. It binds candidate scope, direction, observed time, structure regime, family route identity/version, and 1m precision layer. Hash validity alone is not treated as semantic consistency: nested candidate/gate evidence must agree with the outer family context.
- Hardened the verifier against re-hashed but internally inconsistent candidate payloads, mismatched structure regimes, and precision-timeframe tampering. Authority flags remain immutable false.
- Updated the existing gate pipeline to attach family route/context as diagnostic evidence only. The existing confirmation, risk and final-decision gates remain authoritative; routing does not generate a candidate, pass a gate, or authorize execution.
- Added family ID/version/lifecycle fields to the decision journal and family-level attribution summaries to the matured NO_TRADE validation report. These summaries are regime-based cohort metadata, not strategy P&L or evidence of edge.
- Local validation on the sole VPS working tree: focused family/router/context/pipeline tests **37 passed**; complete repository suite **790 passed**; `git diff --check` passed. The VPS source worktree contains unrelated dirty/untracked material, so these counts are local working-tree evidence, not a clean-main CI result. CI on this PR is still required.
- The currently deployed immutable release remains `3f6ba6c577a6847523099a485e3987d9ac4a5898`; it does not yet include this family-router/context code. No runtime service, active release, strategy activation, policy, execution flag, or order was changed.
- This change is **foundation + attribution only**. Trend breakout remains candidate-locked; range mean reversion remains research-only. No RANGE strategy is activated, and no new signal authority is granted.
