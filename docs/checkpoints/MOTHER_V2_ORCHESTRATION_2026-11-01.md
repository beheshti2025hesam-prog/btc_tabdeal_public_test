# Mother Orchestration + Strategy V2 Integration Checkpoint — 2026-11-01

## Canonical path
- Gate.io Public Spot BTC_USDT is the sole source for live candles, chart and indicators.
- The existing Strategy Policy V2 evaluator consumes the validated Gate.io persisted feed and writes the canonical V2 report and decision journal.
- Mother reads only the existing report plus the exact journal decision whose event ID matches the report's closed 15m candle timestamp.
- Mother does not fetch candles, recompute indicators/structure/strategy/risk, append journal records, infer outcomes or submit orders.
- The independent Mother witness verifies the serialized audit envelope.

## Specialist sequence
1. Data-quality / report-journal identity and provenance.
2. Market structure.
3. Signal-policy evaluation.
4. Confirmation.
5. Risk veto / approval.
6. Decision.
7. Decision-observation evaluation.

A failed stage stops the chain and preserves NO_TRADE. The V2 report's full confirmation/risk details remain available in the canonical V2 projection; Mother records only the stages actually reached. A completed observation is never execution authorization.

## Reproducibility
The following Strategy V2 evaluator sources and regression tests were present in the VPS checkout as untracked files. They have been copied into this PR from the existing working sources so the currently running evaluator is reviewable and reproducible in Git:
- V2 policy, structure/confirmation/risk gate pipeline and final gate.
- Paper risk context and locked V2 strategy specification.
- Gate.io snapshot feature reader and forward evaluator runner.
- Position sizing module and its existing tests.

No new strategy or market-data engine was created.

## Candidate validation
- PR #398 exact head fc0e3b368f6dd79b24e22b34bb0a00a37bd823cf: 30/30 workflow runs successful; full suite 648 passed + 24 subtests.
- PR #405 exact head d0aa9d84dd1ac5ded0a74eb532fa6479ef083d3e: all 3 workflows successful; full suite 654 passed + 24 subtests.
- PR #406 exact head f57988ad042a23478e90b644b6a55852ff8bf2e0: all 3 workflows successful; full suite 689 passed + 24 subtests.
- PR #407 exact head 998adfc90b82a5ccc5d81002127899ce9d4d8351: all 4 workflows successful; full suite 728 passed + 24 subtests.
- PR #407 adds tests for confirmation veto, risk veto, complete observation-only path, stale/missing/mismatched evidence and execution-flag drift.

## Production boundary and remaining release gates
- PR #407 is draft and stacked on #406 → #405 → #398. Do not merge any member independently.
- The production current pointer remains the pre-orchestration release; orchestration and V2 dashboard code are candidate-only.
- No deployment, service restart, production pointer change, account connection or live order was performed.
- Dashboard remains loopback-only; do not expose it beyond loopback/SSH tunnel without separately reviewed authentication and rate-limiting.
- Execution remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. Gate.io is market-data-only; no exchange is approved for leveraged/live execution.
- The exact 24-hour Gate.io persisted-feed soak passed its independent audit: 1,440 samples, 86,400 seconds, zero malformed rows, contiguous IDs, no >90-second gaps, stable source hash, and required feed services active with zero restarts. This validates the recorded soak only; it does not prove profitability, live WebSocket continuity, execution mapping, risk approval or release authorization.
- Delivery target remains 2026-11-19. The 2026-11-04 chart acceptance milestone remains time-critical.