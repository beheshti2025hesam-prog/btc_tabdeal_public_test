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
- Exact current PR head: `9bb1dc7067744e52fa98b8158b932282b13c1b58` (OPEN, Draft, mergeable at last check).
- A real CI failure on preceding head `622d8f5eacbcd4806a937496ce6c6b50ec2dcefc` was traced to Playwright 1.56.1 not supporting the GitHub-hosted Ubuntu 26.04 runner. The existing browser workflow was narrowly fixed to pin `ubuntu-24.04`; no chart, feed, strategy or dashboard implementation was duplicated or changed for this fix.
- **Five exact-head workflows passed on `9bb1dc7067744e52fa98b8158b932282b13c1b58`:**
  - Full repository regression, **611 passed + 19 subtests**: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716943
  - Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716890
  - Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716857
  - Bounded Spot WebSocket smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716982
  - Gate.io public candle contract smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399717171
- Browser artifact ID `13120483810`, ZIP digest `sha256:8bad8bfecd9e40911cdfcd8e0c9e6a0a20d1f3016a29b552f603b3eae2d621de`. Artifact JSON records `status=PASS`, 239 closed candles, same-batch chart/signal hash `eb4eaf64dfaa1eb7244d20fc8a60b7536f6e140480c36c690e81c4cd7685b17b`, close/volume match, all candle values match API batch, responsive 390/768/1440 widths without overflow, no browser market-data request and no external chart CDN.
- Signal remains `BLOCKED / NO_TRADE`; `execution_enabled=false` and `execution_instrument_mapping_verified=false`. This is the expected safe result while execution mapping and independent approvals are absent.
- The bounded WebSocket smoke is a **Binance Spot transport** test only; it is not Gate.io WebSocket recovery evidence. Gate.io stream recovery remains open. The Gate.io REST candle contract smoke passed on this exact SHA.
- These are candidate exact-head CI proofs, not release approval or live execution authorization.
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

- PR #410's five workflows are green on prior documentation-inclusive head `98df5dc...`; the newest documentation-only head is `c4dd3bc...` and has no associated PR-triggered workflow runs in the current check. The workflow evidence verifies the jobs and assertions listed above on their recorded SHA, not the entire production runtime.
- The previously recorded 24-hour persisted Gate.io REST-feed soak audit passed (1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no feed-service restarts) in the #398 lineage. Reuse that evidence; do not rerun it merely to duplicate a report.
- That persisted REST-feed soak does **not** prove Gate.io WebSocket reconnect/recovery, strategy profitability, or execution readiness.
- The blind forward OOS evaluator remains **G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS**. A successful workflow job is not a successful scientific/strategy verdict.
- #408's latest code-head suite remains local/VPS evidence only; its latest documentation head has no Actions runs, and its base branch is behind current #406. Rebase is the earliest dependency blocker before fresh exact-head CI/browser can be accepted.
- No claim of independent human review, independent strategy/structure/confirmation approval, independent risk approval, executable instrument mapping, or live-trading readiness is supported.
- Production and execution remain HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.


### Uploaded sequence-semantics research note
The supplied `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md` is explicitly a 2026-10-10 draft and research-only artifact. Its own limitations say it did not inspect the repository or prove the current implementation. Preserve it as historical protocol research, not as a current Gate.io feed guarantee or release acceptance artifact. The active Gate.io OHLCV/chart path does not depend on individual-trade sequence semantics; do not reopen or port Tabdeal/Binance sequence assumptions into the Gate.io candle reader. Revisit the research only if a concrete execution/order-book feature needs a venue-specific event-identity or ordering contract, and then require current primary evidence plus adapter-scoped tests.

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
| G1 Build and tests | PARTIAL | #410 five exact-head workflows pass on `9bb1dc7...`; #408 requires rebase onto current #406 then exact-head CI/browser |
| G2 Market-data integrity | PARTIAL/PASS for bounded scope | Gate.io 8-field REST schema and same-batch chart/analysis proven; complete WS recovery remains open |
| G3 Runtime resilience | BLOCKED | Gate.io WS disconnect, reconnect, REST reconciliation/backfill, duplicate/gap tests and authorized-runtime soak |
| G4 Frontend integration | PARTIAL | Candidate browser render proven; verify current deployed routes/runtime against reconciled release stack |
| G5 Decision safety | BLOCKED | Independent structure/confirmation/strategy-quality approval and independent risk approval; OOS threshold |
| G6 Execution boundary | BLOCKED / OFF | Authoritative execution venue contract, symbol/instrument mapping, idempotency, order status/fill/fee reconciliation; separate approval |
| G7 Operations/security | PARTIAL | Confirm exact release/runtime lineage, health, recovery and rollback under explicit authorization |
| G8 Review and release | BLOCKED | Reconcile PR stack, independent review, final exact-SHA CI, release notes/runbook/rollback and explicit go/no-go |

A PASS must be tied to exact SHA, run, artifact/hash, scope and limitations. Implemented/reported/skipped/not checked are not PASS.

## 6. Ordered work plan to protect 2026-11-19

1. **2026-11-02 to 2026-11-04:** chart same-batch acceptance evidence is now present on #410 exact head; reconcile #410's relationship to the Mother stack and rebase #408 onto current #406, then obtain exact-head #408 CI/browser. No duplicated chart work.
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

## Execution update — 2026-11-02 (verified after initial checkpoint)

- Fixed the browser smoke runner incompatibility by pinning the existing workflow to Ubuntu 24.04. The subsequent exact-head CI on PR #410 passed 5/5 workflows; full repository suite 611 passed + 19 subtests.
- Browser artifact confirms Gate.io Public Spot BTC_USDT → `global_market_data_reader_v1` is the chart/signal input path; 239 closed candles, identical chart/signal/API batch hash, close/volume and all-candle parity, responsive render at 390/768/1440, no direct browser market-data request. Artifact ZIP SHA-256: `8bad8bfecd9e40911cdfcd8e0c9e6a0a20d1f3016a29b552f603b3eae2d621de`.
- Browser evidence explicitly reports execution instrument mapping unverified, signal BLOCKED/NO_TRADE and execution disabled. This is a correct safety block, not a defect to bypass.
- PR #408 branch ancestry was refreshed: it is 9 commits behind current PR #406 and 32 commits ahead; its base/head have diverged. Rebase/reconciliation is required before exact-head CI and merge evaluation. Do not synthesize a merge tree or overwrite the VPS working tree.
- Uploaded 2026-10-10 sequence-semantics document was read in full. It is research-only and explicitly says no repository diff or implementation proof was reviewed. It does not justify adding sequence logic to the Gate.io candle/indicator path. Keep sequence capabilities adapter-scoped and UNKNOWN unless an actual stream/order-book or execution feature needs them.
- PR #408 received a checkpoint-only update at `43820404038e083022e016146301af8828c65472`; no Actions run was returned for this docs-only commit. Its earlier local code tests remain tied to `f25569a...`, not to the documentation SHA.
