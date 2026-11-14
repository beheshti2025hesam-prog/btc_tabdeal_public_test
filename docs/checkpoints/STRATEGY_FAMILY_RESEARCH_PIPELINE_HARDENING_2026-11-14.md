# Strategy-family research pipeline hardening — 2026-11-14

## Scope
Follow-up hardening to the existing four-family research integration in PR #492. No parallel router, data reader, journal, collector, strategy policy, risk approval or execution path is introduced.

## Defects corrected
1. The pipeline passed the latest candle-close boundary as the market-observation timestamp to the research assessor. It now passes the actual read timestamp separately; the assessor derives the latest fully closed 15m candle boundary from the source rows. The journal projection enforces a non-negative observation lag no greater than 900 seconds.
2. The journal projection expected a single aggregate cost-model status/hash, while the assessor emits cost provenance per family. It now validates the exact assessment version, unique eligible-family IDs and each family's cost status/hash independently. Aggregate cost fields are rejected.

## Live read-only diagnostic
- Source: Gate.io public Spot BTC_USDT.
- Snapshot: 1,261 15m / 1,001 1h / 625 4h rows.
- Regime: UPTREND. Proposal NO_TRADE; Confirmation UNCONFIRMED; Risk RISK_REJECTED; final decision NO_TRADE.
- Trend continuation: 3/5 required features.
- Breakout/Retest: 0/7 required features.
- Range reversion: not compatible with current UPTREND.
- Volatility expansion: 6/8 required features; net-R estimate 1.1603 is assumption-based and missing compression/expansion confirmation.
- No family is research-eligible. Candidate generation, confirmation, risk, execution and order authority remain false.
- The 15m candle boundary was 09:15:00 UTC; market observation was 09:20:36.361 UTC (336.361 seconds). The live assessment passed the journal projection validator.

## Validation
- 298 tests passed across tests/strategy and the journal projection; 7 subtests passed.
- 71 focused dispatcher/features/pipeline/learning/journal tests passed.
- Python compile and git diff --check passed.
- The pre-existing PR #492 full-suite evidence (1,325 passed + 82 subtests) applies to its prior code head; this follow-up has its own targeted test result and must receive exact-head CI.

## Operational provenance note
A candidate learning-loop script was accidentally invoked with --help even though it has no CLI help parser. It ran two READ_ONLY_HYPOTHESIS_ONLY cycles against the shared forward-data root before being terminated. It appended two HYPOTHESIS_ONLY entries and refreshed learning/diagnostic reports/state; it did not append to the trade journal, candidate ledger or outcome ledger and did not mutate strategy policy, risk approval, execution or orders. The active systemd learning service was not restarted. Do not invoke this script directly for help; inspect source or run its tests.

## Status
Candidate hardening only. PR #492 remains OPEN / DRAFT. No production deployment, paper-policy activation or live order is authorized by this change. The 24-hour Gate.io soak and all independent risk, paper-performance, cost-model and backup/restore gates remain separate.