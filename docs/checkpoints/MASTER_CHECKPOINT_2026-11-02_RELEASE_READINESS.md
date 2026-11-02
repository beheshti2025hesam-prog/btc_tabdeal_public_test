# HES Trade Agent — Master Checkpoint: Release Readiness & Documentation

**Checkpoint date:** 2026-11-02 (UTC)  
**Target delivery:** 2026-11-19  
**Purpose:** resume from the current evidence and release state without rediscovery, duplicate implementation, or denominator drift.

> **Project memory contract:** Memory = project map/context; GitHub = technical truth; Chat = conversation log.  
> **Release disposition:** HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. This checkpoint does not authorize merge, production pointer change, deployment, service mutation, account connection, execution enablement, or live orders.

## 1. Locked architecture and non-negotiable constraints

- **Gate.io Public Spot BTC_USDT is the sole canonical market-data source** for live market data, chart, candles and indicators through the existing persisted feed and `global_market_data_reader_v1`.
- The execution venue adapter is separate and is used only for order submission/status/fill reconciliation after independent authorization. Do not obtain or reconcile analysis candles from the execution exchange.
- Reuse the existing `NativeOHLCVBatch`, Gate.io reader/collector, native feature pipeline, `StrategyEvidenceProviderV1`, `SignalAgentV1`, Strategy Policy V2, canonical decision journal, Mother Orchestrator, independent witness, News Intelligence Brain, Learning Loop and existing dashboard entrypoint.
- No second candle engine, indicator pipeline, strategy, dashboard, journal, news monitor, or competing checkpoint.
- Gate.io fields unavailable from the documented source (including trade count/taker-buy flow where absent) remain UNKNOWN; never fabricate or silently substitute zero.
- One VPS only. Preserve the dirty VPS working tree; do not reset, clean, checkout over, or overwrite it.
- Sequence-semantics research is a versioned, adapter-specific control plane; do not reopen settled venue investigations or use opaque exchange sequence values as generic event IDs.
- All missing, stale, gapped, malformed, mismatched, unprovenanced or unapproved evidence fails closed.

## 2. Current verified repository and candidate state

Canonical repository: `beheshti2025hesam-prog/btc_tabdeal_public_test`. Default branch: `main`. The connected GitHub account currently has push/admin permission on this repository.

### PR #410 — Gate.io candle contract + existing Signal Agent wiring

- URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/410
- State at checkpoint: OPEN, Draft, unmerged.
- Branch: `fix/gateio-signal-strategy-wiring-20261029`.
- Exact current head: `98df5dc9485f3d0ae564b7093dff17e1324a87dd`.
- Executable candidate code head previously tested: `b7fef1132e65729bd2d40e1d0d98cd948983ca48`; later commits in this checkpoint lineage are documentation-only. Exact-head Actions also completed on current PR head `98df5dc...`.
- Five PR-triggered workflows on the current head completed successfully:
  - Full repository regression: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41339254312
  - Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41339254341
  - Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41339254344
  - Bounded live Spot WebSocket-to-REST smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41339254318
  - Gate.io public candle contract smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41339254363
- Every listed workflow's exact-revision assertion and job concluded SUCCESS. The WebSocket smoke is a bounded one-candle transport/reconciliation test; it is **not** proof of Gate.io's full disconnect/reconnect/recovery behavior or a 24-hour WebSocket soak.
- Existing candidate evidence: chart and Signal Agent consume the same persisted Gate.io batch; 239 closed candles rendered; responsive widths 390/768/1440; no browser-to-exchange market-data request; decision remains BLOCKED / NO_TRADE and execution disabled.
- Gate.io Spot candle schema is versioned as `gateio_spot_candlestick_v2`; the adapter validates all 8 fields including the closed-window flag, excludes open bars and fails closed for missing/invalid flags.
- Gate.io trade-count/taker-buy values not supplied by this source remain UNKNOWN.
- PR #410 remains candidate-only. Green CI does not constitute independent strategy/risk approval or release authorization.

### PR #408 — Mother V2 integration and numeric hardening

- URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/408
- State: OPEN, Draft; current exact head `f25569a7d22e4e9382d05e9df61e5142b9381ce3`; not mergeable in its current stacked state.
- Latest local/VPS exact-head suite reported: 742 passed + 66 subtests (9.58s); focused risk/Strategy V2 tests: 24 passed + 42 subtests.
- **No GitHub Actions PR-triggered runs were returned for this exact SHA**. Earlier 4/4 workflow successes and browser evidence belong to the earlier head `c0f1d22...` and must not be transferred to `f25569a...`.
- Numeric hardening rejects booleans, non-numeric, non-finite, oversized values, invalid RSI/MFI ranges, and invalid risk fraction/RR before arithmetic. The current candidate remains read-only and fail-closed.
- Do not merge #408 independently or bypass its dependency chain.

### Stacked dashboard/Mother dependency chain

- Current documented sequence: **#398 → #405 → #406 → #408**. Reconfirm exact ancestry, mergeability and exact-head checks immediately before any release action.
- #407 is the superseded, non-mergeable predecessor; #408 is its rebased successor. Avoid duplicate work on #407.
- #410 is a separate Gate.io/Signal Agent candidate; do not assume it is automatically included in the #398→#408 stack.

## 3. Release evidence and honest interpretation

- Current PR #410 workflows are green on the exact current documentation-inclusive head. This verifies the jobs and assertions listed above, not the entire production runtime.
- The previously recorded 24-hour persisted Gate.io REST-feed soak audit passed (1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no feed-service restarts) in the #398 lineage. Reuse that evidence; do not rerun it merely to duplicate a report.
- That persisted REST-feed soak does **not** prove Gate.io WebSocket reconnect/recovery, strategy profitability, or execution readiness.
- The blind forward OOS evaluator remains **G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS**. A successful workflow job is not a successful scientific/strategy verdict.
- Earlier #408 browser and full-suite evidence is stale for the newer #408 SHA. Current #408 full suite is locally reported only, pending exact-head GitHub Actions and browser evidence.
- No claim of independent human review, independent strategy/structure/confirmation approval, independent risk approval, executable instrument mapping, or live-trading readiness is supported.
- Production and execution remain HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.

## 4. Fixed-weight project progress model

Keep the existing fixed model v1 denominator; do not change weights or compare with older rough percentages. Last evidence-weighted calculation was **64.04% (~64%) overall project completion** and **20% release readiness**. This checkpoint does not invent a new percentage from passing workflows alone. Update scores only after scoring each workstream against new evidence and preserving the same rubric.

| Workstream | Weight | Last estimate | Main remaining proof |
|---|---:|---:|---|
| Gate.io data foundation / collectors | 15% | 90% | Gate.io WS recovery and release-runtime lineage |
| Features, structure, strategy, Signal Agent | 18% | 68% | Independent strategy/structure/confirmation acceptance; OOS observations |
| Risk, decision gates, Mother, witness | 14% | 65% | Independent risk approval and complete runtime proof |
| Journal, forward evaluation, Learning Loop | 10% | 60% | More valid forward observations and end-to-end runtime evidence |
| Dashboard/frontend/API | 10% | 68% | Reconciled release stack and deployed-route proof |
| News Radar / multi-market roadmap | 10% | 35% | Qualified sources, adapters and multi-venue acceptance |
| Tests, provenance, CI | 10% | 75% | Gate.io WS recovery proof, exact candidate evidence and review |
| VPS operations/security/recovery | 8% | 55% | Authorized-runtime soak/restart and lineage proof |
| Release readiness | 5% | 20% | All mandatory gates, rollback, review and explicit go/no-go |

Overall estimate is planning evidence, not code coverage, profitability, or permission to deploy.

## 5. Release gates — status at 2026-11-02

| Gate | Current status | Remaining evidence / action |
|---|---|---|
| G0 Scope and lineage | PARTIAL | Reconfirm exact PR ancestry and VPS runtime lineage; preserve dirty worktree |
| G1 Build and tests | PARTIAL | #410 exact-head workflows pass; #408 current SHA still needs exact-head Actions/browser |
| G2 Market-data integrity | PARTIAL/PASS for bounded scope | Gate.io 8-field REST schema and same-batch chart/analysis proven; complete WS recovery remains open |
| G3 Runtime resilience | BLOCKED | Gate.io WS disconnect, reconnect, REST reconciliation/backfill, duplicate/gap tests and authorized-runtime soak |
| G4 Frontend integration | PARTIAL | Candidate browser render proven; verify current deployed routes/runtime against reconciled release stack |
| G5 Decision safety | BLOCKED | Independent structure/confirmation/strategy-quality approval and independent risk approval; OOS threshold |
| G6 Execution boundary | BLOCKED / OFF | Authoritative execution venue contract, symbol/instrument mapping, idempotency, order status/fill/fee reconciliation; separate approval |
| G7 Operations/security | PARTIAL | Confirm exact release/runtime lineage, health, recovery and rollback under explicit authorization |
| G8 Review and release | BLOCKED | Reconcile PR stack, independent review, final exact-SHA CI, release notes/runbook/rollback and explicit go/no-go |

A PASS must be tied to exact SHA, run, artifact/hash, scope and limitations. Implemented/reported/skipped/not checked are not PASS.

## 6. Ordered work plan to protect 2026-11-19

1. **2026-11-02 to 2026-11-04:** keep chart acceptance as the immediate milestone; obtain exact-head #408 Actions/browser evidence; validate #410 current evidence and reconcile its relationship to the main stack. No duplicated chart work.
2. **2026-11-05 to 2026-11-09:** complete Gate.io WebSocket recovery/fault-injection evidence using the existing collector; verify runtime lineage and authorized-runtime soak without disturbing the dirty VPS checkout.
3. **2026-11-10 to 2026-11-12:** obtain independent strategy/structure/confirmation and risk review; verify execution instrument mapping from authoritative venue contract while keeping execution OFF. Freeze scope on Nov 12.
4. **2026-11-13 to 2026-11-16:** reconcile the complete non-overlapping PR stack; run exact-final-SHA CI/browser checks; prepare release notes, known limitations, configuration/secret handling, operator runbook, health checks and rollback.
5. **2026-11-17 to 2026-11-18:** final go/no-go. Any mandatory gate still open means no production-ready claim; deliver only verified read-only/paper scope.
6. **2026-11-19:** target delivery of only the scope whose gates passed. Software delivery never implies trading authorization.

## 7. Anti-duplication and 20-year maintainability rules

- Search existing code, PRs, workflows, tests, schemas and docs before adding anything; prefer reuse and narrow optimization.
- Keep one source of truth for market data and one canonical event/journal path.
- Version schemas/contracts and migrations; never silently reinterpret historical data.
- Every operational evidence record must include UTC timestamp, exact SHA, source/endpoint/product/symbol/timeframe, run URL, artifact/hash, result, limitations and provenance.
- Keep unknown values explicit; fail closed on schema drift, stale data, gaps, identity mismatch, clock anomalies and missing evidence.
- Add deterministic replay/negative tests for every new contract; use bounded read-only probes by default.
- Pin dependencies, document supported versions, ownership, update cadence, backup/restore and end-of-life. Prefer portable/free-first interfaces and avoid unnecessary paid runtime dependencies.
- Keep operator actions least-privilege and explicitly allow-listed. Never place secrets in logs, checkpoints, CI artifacts or prompts.
- Preserve append-only audit evidence; corrections are new versioned records, not silent edits.
- Maintain a single latest checkpoint index and immutable dated snapshots. Do not create parallel project plans.

## 8. Resume instruction

Resume from this checkpoint. First refresh exact PR heads/status and the earliest unmet release gate. Continue only with existing code paths. Never infer approval from a green workflow. No merge, production deployment, service restart, pointer change, account connection or order execution without explicit authorization and all mandatory gates passing.
