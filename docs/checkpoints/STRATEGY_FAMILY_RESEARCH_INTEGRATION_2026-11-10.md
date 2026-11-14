# HES Trade Agent — Four-Family Research Evidence Integration

**Date:** 2026-11-10  
**Base:** PR #491 head `d031203300c4c9ba4cc76dcf1a7504696a4e2d58` (which is stacked on PR #480).  
**Disposition:** IMPLEMENTED AND FULL-SUITE TESTED IN AN ISOLATED WORKTREE / NOT YET PUBLISHED AS A FOLLOW-UP PR / NOT DEPLOYED.

## Reused architecture and delivered integration

- Reused the existing persisted `global_market_data_reader_v1` Gate.io Spot BTC_USDT feed; no new network reader, exchange source, collector, router, journal, outcome ledger or service was added.
- Closed 15m candles remain the sole setup authority. The existing 1m precision path remains downstream only.
- Reused `StrategyEvidenceProviderV1`, the existing Trend opportunity detector and `StrategyPolicyV1` quorum, the existing eight-check Range evidence builder, the causal structure events, and the shared Risk Gate.
- The PR #491 research dispatcher is now the single canonical four-family eligibility contract. Each family has a versioned, explicit feature list; feature keys are family-specific to avoid accidental cross-family evidence reuse.
- Range evidence is attributed to its actual eight existing checks: candidate validity, range persistence, boundary location, reversal trigger, direction/regime alignment, directional flow, structure confirmation and cost-adjusted geometry. Direction and cost-context binding are separately validated.
- Breakout/Retest and Volatility Expansion use causal features from the same bounded closed 15m OHLCV window. No trade-count or taker-buy fields are invented.
- Research eligibility remains distinct from candidate generation, confirmation, Risk approval, strategy activation and execution. Every family result explicitly preserves all authority flags as false.

## Integrity hardening

- Every adjacent 15m candle must have the exact 900-second interval; gaps, overlaps and malformed intervals block assessment.
- `observed_at` is now the exact latest closed-candle boundary. `market_observed_at` separately records the persisted-feed observation time. Their relationship is checked for staleness, hashed and verified by the journal projection.
- The journal verifies the four-family set, canonical family versions, required features, feature booleans, per-family evidence digests, source-window hash, cost-model binding and all execution flags.
- The read-only learning loop derives family-specific HYPOTHESIS_ONLY diagnostics from the validated existing journal projection. It cannot mutate policy or count research eligibility as a resolved trade.
- The existing dashboard now shows the latest four-family research state, direction, feature coverage, estimated net-R and cost status, with per-family feature details in tooltips.

## Read-only persisted Gate.io snapshot diagnostic

- Loaded the existing persisted reader input only: 903 15m rows, 911 1h rows and 602 4h rows.
- Snapshot observation: `2026-11-10T16:00:06.377Z`; latest closed 15m boundary: `2026-11-10T16:00:00Z`.
- Regime: RANGE.
- Trend Continuation: not eligible because the current regime is not directional.
- Breakout/Retest: research eligible, direction SHORT; estimated net R 1.1346 under assumption-based simulation costs.
- Volatility Expansion: research eligible, direction SHORT; estimated net R 1.1346 under the same assumption-based cost model.
- Range Reversion: not eligible; the existing Range evidence builder returned no candidate and its required checks were not met.
- The final decision remained `NO_TRADE`; the shared Risk Gate remained `RISK_REJECTED`; `execution_enabled=false`; `orders_placed=false`.
- Replaying the same snapshot with the research assessor enabled and disabled produced identical values for every pre-existing gate output field. Only the new research-assessment field differed.

This is a one-snapshot diagnostic, **not** a backtest, trade signal, resolved outcome, profitability proof, or verified-cost result. Research eligibility does not authorize a candidate or trade.

## Verification

- Focused dispatcher/features/pipeline/journal/learning tests: **69 passed**, warnings treated as errors.
- Full isolated repository suite: **1,325 passed + 82 subtests**, warnings treated as errors.
- Python compilation: passed.
- Dashboard JavaScript syntax check: passed.
- `git diff --check`: passed.
- Primary production checkout `/opt/hes-trade-agent` was not modified; active release pointer and services were not changed.

## Remaining gates

1. Publish the additive integration on a new draft PR stacked on PR #491; run exact-head CI and obtain independent review.
2. Keep all four families research-only; do not alter the common Risk Gate, 3R policy, position sizing or execution adapter.
3. Collect family-isolated forward paper outcomes with no retroactive attribution; require sufficient resolved cohorts, verified execution-product fees/spread/slippage, positive net expectancy, PF > 1, drawdown/tail-risk review and independent chronological OOS evidence before promotion.
4. Complete immutable release, encrypted Dropbox backup and restore verification as separate gates. No production deployment, service restart, account access or live order is authorized by this checkpoint.

**Invariant:** `candidate_generation_authorized=false`; `confirmation_approved=false`; `risk_approved=false`; `execution_enabled=false`; `orders_placed=false`.

## Follow-up hardening — 2026-11-14

PR #492 exact branch head is 099433d2bdd2bb5b030cb3fa3b18eb479fb340bb; its exact-head GitHub Actions are now 3/3 successful (Gate.io Dashboard Full Repository Regression #742, Native OHLCV Dashboard Single Path #995, Native OHLCV Browser Render Smoke #1003). It remains OPEN / DRAFT and stacked on PR #491.

A local follow-up candidate was tested against the live persisted Gate.io snapshot without writing to the decision journal:
- 1,261 15m / 1,001 1h / 625 4h rows; regime UPTREND.
- No family is research-eligible at this snapshot. Trend: 3/5 required features; Breakout/Retest: 0/7; Range: regime incompatible; Volatility Expansion: 6/8, with estimated net R 1.1603 under assumption-based costs but missing compression/expansion confirmation.
- Final decision remains NO_TRADE; Confirmation UNCONFIRMED; Risk RISK_REJECTED; all candidate-generation, confirmation, risk, execution and order authority flags remain false.
- Closed 15m candle boundary 09:15:00 UTC and actual market-observation timestamp 09:20:36.361 UTC are now separately bound (336.361-second lag). The journal projection accepted the live four-family assessment.

Two integration defects were found and fixed in the isolated candidate:
1. The pipeline had passed the candle-close timestamp as market-observation time to the family assessor. It now passes the actual read timestamp while the assessor derives the latest fully closed 15m candle boundary from the data.
2. The journal projection expected one aggregate cost-model status/hash, but the assessor emits cost provenance per family (ASSUMPTION_BASED or UNAVAILABLE). The projection now validates the exact assessment version, unique eligible-family IDs, and each family's cost status/hash independently; it rejects unsupported aggregate fields and malformed future VERIFIED cost claims.

Validation: 298 tests passed across the strategy suite and journal projection, including 7 subtests; 71 focused tests also passed; Python compile and git diff --check passed. These changes remain isolated in the dirty strategy worktree and are not in production. Candidate follow-up PR publication and exact-head CI are still pending.

Operational note: a candidate learning-loop script was mistakenly invoked with --help even though it has no CLI help parser. It ran two READ_ONLY_HYPOTHESIS_ONLY cycles against the shared forward-data root before being terminated. It appended two HYPOTHESIS_ONLY entries (no policy mutation), updated only learning/diagnostic reports/state, and did not append to the trade journal, candidate ledger or outcome ledger. No strategy policy, Risk approval, execution flag, order or service was changed. Do not invoke the learning-loop script directly for help; use its tests or inspect its parser/source. The active systemd learning service was not restarted.