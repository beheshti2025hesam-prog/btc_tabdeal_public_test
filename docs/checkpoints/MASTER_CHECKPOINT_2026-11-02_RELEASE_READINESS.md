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

### PR #410 — Gate.io collector, native adapter and Signal Agent wiring

- URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/410
- State: OPEN, Draft, unmerged; GitHub reports mergeable. Latest code-bearing SHA: `a0abac7d23893cf8d628041d8033ec9b5bee119e`. Later checkpoint/release-doc updates are documentation-only; CI claims remain tied to this exact code SHA.
- **All five exact-head workflows passed**:
  - Full repository regression, **628 passed + 19 subtests**: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41403395583
  - Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41403395695
  - Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41403395666
  - Native WebSocket live smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41403395650 (**Binance Spot**, not Gate.io recovery evidence)
  - Gate.io public candle contract smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41403395640
- Browser artifact ID `13121903096`, SHA-256 `92ca42d3941ea0ff435af87b351cb20f02d226b7387648404cb36f2ed28d7296`. The browser render/responsive workflow passed on this exact candidate.
- The existing Gate.io collector, previously present on the VPS working branch but absent from the release PR chain, is now versioned here. This is the existing collector, not a second implementation:
  - `forward/global_market_data_gateio_v1.py`, service wrapper, read-only 24h soak script and operator README.
  - 15m/1h/4h systemd units, matching UMask/sandbox drop-ins, and optional soak unit.
  - Portable deterministic collector tests.
- The collector reuses `GateioSpotKlineSource` for the canonical eight-field REST parser. WebSocket messages are validated wake-up notifications only; both base-volume `a` and quote-volume `v` must exist, neither is substituted, and persisted candle records always come from the shared REST adapter.
- It maintains at most 500 contiguous closed candles, reconciles by open time, atomically repairs missing recent bars when the REST window contains them, and fails closed on malformed rows, conflicting duplicates or unresolved gaps. REST reconciliation runs at least every 20 seconds while subscribed; reconnect uses bounded exponential backoff.
- Targeted Gate.io collector/native-adapter/reader suite: **33 passed**. Full repository suite passed locally and in GitHub Actions: **628 passed + 19 subtests**. `systemd-analyze verify` accepted the four unit files; its only warning was for an unrelated pre-existing Xray unit.
- The browser-facing dashboard stream remains disabled by design. The backend collector uses Gate.io WS as a wake-up and REST for persisted closed-candle values. The Binance Spot smoke is not evidence of Gate.io WS recovery.
- This collector change is candidate-only and **not deployed**. Current VPS services remain on the pre-existing dirty runtime checkout; no service was restarted or changed.
- Gate.io schema `gateio_spot_candlestick_v2` validates all eight REST fields and the closed-window flag; open bars are excluded. Trade-count/taker-buy values not supplied by the source remain UNKNOWN.
- Signal remains `BLOCKED / NO_TRADE`; execution remains OFF and execution instrument mapping remains unverified. Green CI is not release or trading authorization.

### PR #408 — Mother V2 integration and numeric hardening

- URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/408
- State: OPEN, Draft, GitHub reports mergeable. Exact head: `cf2fad0c7363a33181bc94c3b2e4f6155d8b0a72`; base is current PR #406 head `9d761f0c7b140de52a3a7a1afc3f8e0ad7154927`; zero commits behind.
- The pre-rebase branch is preserved at `archive/pr-408-pre-rebase-2026-11-02`. The rebase omitted duplicate code already present in the updated parent; no production or original VPS checkout was overwritten.
- Exact-head Actions passed **4/4**:
  - Full repository regression: **791 passed + 64 subtests**: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900557
  - Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900566
  - Blind forward OOS evaluator workflow: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900552
  - Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900603
- The same full suite passed in the clean VPS-side rebase clone: 791 passed + 64 subtests. The original dirty checkout at `/opt/hes-trade-agent` remained untouched.
- Browser artifact ID `13122300672`, ZIP SHA-256 `ed89e67dcfec6ad79247aaace3dfab57023045222ae772da68796bea380eb2aa`: PASS; Gate.io Public Spot BTC_USDT via `global_market_data_reader_v1`; 239 closed candles; latest bar age 55.5s; same-batch chart/API/all-candle parity; close and volume match; responsive 390/768/1440 without overflow; no browser market-data request or external chart CDN.
- Browser artifact reports `strategy_v2_status=BLOCKED`, `NO_TRADE`, and `execution_instrument_mapping_verified=false`; execution remains OFF.
- Reconciled `OpportunityPolicyV1` to explicit symbol/timeframe scopes. Default is Gate.io `BTC_USDT/15m`; other scopes must be passed explicitly. No implicit venue-symbol rewrite.
- Preserved the journal's backward compatibility for legacy rows without `event_id`; corrected tests to verify legacy preservation and append defaults.
- Fixed escaped-newline test fixture and isolated collector final-checkpoint unit tests from real Git synchronization/reset. Made three forward-report tests resolve scripts relative to the repository root rather than hard-coded `/opt/hes-trade-agent`.
- The OOS workflow completed, but its scientific verdict remains `G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS`: 95 forward observations vs 4,000 required. Its frozen source is legacy `data/trades.csv` (Tabdeal trade-event data, source commit `f396de84...`), not the canonical Gate.io candle source. It is not evidence of current Gate.io strategy profitability or approval.
- Do not merge independently or bypass the #398 → #405 → #406 dependency chain.

### Stacked dashboard/Mother dependency chain

- Current documented sequence: **#398 → #405 → #406 → #408**. Reconfirm exact ancestry, mergeability and exact-head checks immediately before any release action.
- #407 is the superseded, non-mergeable predecessor; #408 is its rebased successor. Avoid duplicate work on #407.
- #410 is a separate Gate.io/Signal Agent candidate; do not assume it is automatically included in the #398→#408 stack.

## 3. Release evidence and honest interpretation

- PR #410's five workflows pass on exact code SHA `9bb1dc7...` (later docs-only branch head `b8f019c...`). PR #408's four workflows pass on exact head `cf2fad0...`. These prove the listed candidate scopes only, not production runtime or profitability.
- The previously recorded 24-hour persisted Gate.io REST-feed soak audit passed (1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no feed-service restarts) in the #398 lineage. Reuse that evidence; do not rerun it merely to duplicate a report.
- The current architecture uses Gate.io persisted REST closed candles for chart/analysis. The backend collector uses Gate.io WebSocket only as a wake-up channel and reuses the native REST adapter for persisted values. The browser-facing stream remains disabled. The REST soak does not prove live WS reconnect/recovery after an induced outage, strategy profitability, or execution readiness.
- The blind forward OOS evaluator remains **G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS**. A successful workflow job is not a successful scientific/strategy verdict.
- #408 is now based on current #406 head, mergeable, and exact-head CI/browser passed. Remaining work is the complete dependency-stack review and final combined-release SHA validation.
- No claim of independent human review, independent strategy/structure/confirmation approval, independent risk approval, executable instrument mapping, or live-trading readiness is supported.
- Production and execution remain HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.


### Uploaded sequence-semantics research note
The supplied `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md` is explicitly a 2026-10-10 draft and research-only artifact. Its own limitations say it did not inspect the repository or prove the current implementation. Preserve it as historical protocol research, not as a current Gate.io feed guarantee or release acceptance artifact. The active Gate.io OHLCV/chart path does not depend on individual-trade sequence semantics; do not reopen or port Tabdeal/Binance sequence assumptions into the Gate.io candle reader. Revisit the research only if a concrete execution/order-book feature needs a venue-specific event-identity or ordering contract, and then require current primary evidence plus adapter-scoped tests.

## 4. Fixed-weight project progress model

Keep the existing fixed model v1 denominator; do not change weights or compare with older rough percentages. Last evidence-weighted calculation was **64.04% (~64%) overall project completion** and **20% release readiness**. This checkpoint does not invent a new percentage from passing workflows alone. Update scores only after scoring each workstream against new evidence and preserving the same rubric.

| Workstream | Weight | Last estimate | Main remaining proof |
|---|---:|---:|---|
| Gate.io data foundation / collectors | 15% | 90% | Live WS/REST fault-injection evidence and release-runtime lineage |
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

## Latest execution update — 2026-11-02 (candidate CI and read-only VPS audit)

### Gate.io feed and runtime

- The three existing Gate.io candle collector services (15m, 1h, 4h), readonly dashboard, paper evaluator and learning loop were all ACTIVE with `NRestarts=0` at the audit. Persisted candle files were current at 06:15Z (15m), 06:00Z (1h), and 04:00Z (4h).
- The browser artifact on PR #408 proves 239 closed bars, same-batch chart/API parity, and latest closed-bar age 55.5 seconds. The browser-facing dashboard stream is disabled; no browser market-data request is made.
- The backend Gate.io collector uses WS messages as wake-up notifications and persists candles only through the shared native REST adapter. The new versioned candidate adds 20-second REST reconciliation, bounded reconnect, atomic recent-window backfill and fail-closed duplicate/gap checks. Deterministic tests cover reconnect/backoff, REST-only persistence after WS close notification, gap repair and conflict rejection.
- Candidate collector code and service templates are in PR #410 exact code SHA `a0abac7...`, with 5/5 workflows green and 628 repository tests + 19 subtests. **It has not been deployed.** Current VPS services still run the pre-existing runtime checkout; do not claim the candidate fixes are active on the VPS.
- The backend WS subscription itself was not independently verified from service logs in this read-only audit. The prior 24-hour Gate.io REST-feed soak passed (1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no service restarts); reuse that evidence. Live WS/REST fault-injection remains open.
- Runtime lineage is not yet reconciled: dashboard service runs from `/opt/hes-trade-agent/current` → `releases/2e8d3859...`; paper evaluator and learning loop run from `/opt/hes-trade-agent` root, branch `feat/gateio-global-market-data-v1`, SHA `060d0d36...`, with a dirty worktree. All six relevant services remained ACTIVE with `NRestarts=0`. This was read-only inspected and left untouched. Release G0/G4/G7 remain partial until code roots are reconciled.

### Current paper journal and Learning Loop snapshot

- 24h decision report generated 06:27Z: 96 NO_TRADE decisions.
- 95 decisions have complete, gap-free 24h forward windows; one recent decision is not yet mature. No gate-qualified directional counterfactual has established an avoided loss or missed profit. A rejected proposal's later stop-loss touch is diagnostic only, not a counted avoided loss.
- Learning Loop remains `READ_ONLY_HYPOTHESIS_ONLY`; target policy is unset; `policy_mutation_enabled=false`, `execution_enabled=false`, `orders_placed=false`. No thresholds or strategy policy were tuned from these observations.

### OOS source qualification

- The blind OOS workflow completed successfully as a workflow, but the verdict is still `G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS` (95 forward observations vs 4,000 required).
- Its frozen source `data/trades.csv` is legacy Tabdeal trade-event data, not the canonical Gate.io candle feed. Preserve the old artifact as historical research only; it cannot approve the current Gate.io strategy. The Gate.io-based decision journal is the current forward evidence path.

### Documentation consolidation completed

- Updated `docs/PROJECT_DNA.md` with the Gate.io single-source boundary for the current BTC_USDT release, the separate execution adapter, the no-reinvention rule, 20-year maintainability controls, the two-person operating model, and the GitHub/Master Checkpoint source-of-truth contract.
- Updated `docs/release/HES_DASHBOARD_SECURITY_RELEASE_ROLLBACK_RUNBOOK.md` to distinguish the backend Gate.io WS/REST collector from the disabled browser-facing stream, keep collector services separate from dashboard pointer changes, and record current exact-SHA evidence and remaining release gates.
- Updated `docs/RELEASE_READINESS.md` and `deploy/systemd/README.md`; the existing Gate.io service templates and soak procedure are now discoverable from the release documentation.
- These are documentation-only changes after code-bearing PR #410 SHA `a0abac7...`; no new code validation is claimed for documentation commits.

### Safe execution boundary and original workspace preservation

- The uploaded sequence-semantics document was read in full. It is research-only and does not justify applying trade-sequence logic to the Gate.io OHLCV candle path. Venue sequence semantics remain adapter-specific and UNKNOWN unless a concrete execution/order-book feature needs them.
- The original dirty VPS checkout remains at SHA `060d0d36ae6140a03d9a74495bb3899637ed3827`; it was not reset, cleaned, checked out over, or overwritten. Candidate work was isolated under `/tmp/hes-pr408-rebase-20261102` and `/tmp/hes-pr410-gateio-collector-20261102`; a pre-rebase backup branch exists.
- No PR merged; no service restarted; no production pointer changed; no exchange account connected; no order executed. Delivery target remains **2026-11-19**.


## Continuation update — 2026-11-02 (collector reproducibility + tests)

### Exact current branch and candidate evidence

- PR #410 remains OPEN/Draft/unmerged and mergeable. Current exact head at this audit: `daa7d9f1d48bc132e1c6a5c5c1558d2e0cf0b156`; base branch `integration/gateio-persisted-feed-signal-agent-20261026`, base SHA `2e8d3859ef154b030e0965ad4479f3fad36ae4c0`.
- Five PR-triggered Actions workflows are green on the exact current head: full repository regression, native OHLCV single path, browser render, bounded WS smoke, Gate.io candle contract smoke. These runs prove the candidate state only; no merge or production deployment is implied.
- A separate isolated candidate checkout ran the Gate.io collector + canonical reader tests: **23 passed** (0.30s), and Python compileall passed for collector, service wrapper and 24h soak script. This is local VPS-side validation, not a GitHub Actions artifact. The isolated checkout was rebased onto current remote; the local commit was dropped because identical patch content was already upstream. No force-push was performed.

### Existing collector reproducibility and semantic fix

- The existing Gate.io collector, 15m/1h/4h systemd unit templates, security/sandbox drop-ins, optional 24h read-only soak unit, wrapper, README and focused tests are now present in the PR branch; no second collector was introduced.
- Collector REST bootstrap/reconciliation reuses `GateioSpotKlineSource` and the canonical `gateio_spot_candlestick_v2` adapter contract. Internal key `BTCUSDT` → persisted venue symbol `BTC_USDT` mapping is explicit.
- Corrected WS semantic mapping: Gate.io `a` is base volume and `v` is quote volume. Missing base or quote volume is rejected; quote volume is never silently substituted for base volume. Unsupported trade count/taker-buy flow stays UNKNOWN.
- Reconciliation is keyed by candle open time, idempotent for identical rows, repairs missing recent candles from REST, and fails closed on conflicting duplicates, malformed identity/numerics, unresolved gaps or non-closed rows. Snapshot writes use temp-file + fsync + atomic replace. These behaviours have focused tests.
- The 24h soak script now resolves repository-relative paths and accepts an explicit output path. Systemd templates document the existing VPS layout; they are not installed/restarted by this code change.

### Explicit limitations and next gates

- Existing runtime services remain untouched. Do not assume the newly versioned templates have been installed or that deployed service/runtime parity is proven.
- Keep Gate.io public Spot REST closed candles as the canonical chart/analysis feed. WS is a supplemental collector transport, not a browser data path and not a second analytical source. REST reconciliation remains authoritative.
- Do not claim 24h collector recovery is newly proven by the 23-test unit run. Deterministic process restart/backfill fault injection and deployed runtime parity remain open release gates.
- The source-to-render chart proof and current PR CI remain candidate evidence. Full dependency-stack final-SHA reconciliation, independent strategy/risk review, sufficient Gate.io forward observations, authoritative execution instrument mapping, rollback/restore evidence and explicit go/no-go remain required.
- No PR merged; no live service restarted; no current-pointer change; no exchange account connection; no order executed. Execution remains disabled.

### Full-suite result added after focused tests

- On isolated checkout at code-bearing SHA `daa7d9f1d48bc132e1c6a5c5c1558d2e0cf0b156`, full repository test suite passed: **628 passed, 19 subtests passed (5.98s)**. This is local execution evidence; the five GitHub Actions runs are separately tied to the same code-bearing SHA. Documentation-only commits after this SHA are not claimed as independently rerun.


## Runtime health and live-analysis checkpoint — 2026-11-02

### Live VPS evidence (read-only inspection)

- All three existing collector services were `active/running`: `hes-global-market-data-gateio.service`, `hes-global-market-data-gateio-1h.service`, `hes-global-market-data-gateio-4h.service`. Their current main PIDs were 687, 685, 686; each reported `NRestarts=0` and the last service start was 2026-10-28 06:33:50 UTC. No service was restarted or reloaded.
- Persisted feed integrity scan: 15m 1,347 rows, 1h 711 rows, 4h 552 rows. All rows parsed; all were closed, ordered, unique, and had zero interval gaps; source/symbol/timeframe identity was inspected via the existing reader contract. Latest open times: 15m 2026-11-02 06:45 UTC, 1h 06:00 UTC, 4h 00:00 UTC. The scan time showed the last closed candle age below the reader's 2-interval stale threshold. This is a point-in-time integrity check, not a new 24h soak or reconnect fault-injection proof.
- Ran the existing `scripts/run_gateio_analysis_v1.py` against persisted Gate.io closed candles. It wrote the existing decision snapshot `data/forward/gateio_analysis_decision_v1.json`: observed_at `2026-11-02T07:00:00Z`, source `gateio_public_spot`, symbol `BTC_USDT`, timeframe `15m`, decision `NO_TRADE`, direction `NONE`, regime `UNKNOWN`, reason `NO_CANDIDATE`, confirmation `NOT_CONFIGURED`, risk `RISK_NOT_APPROVED`, `execution_enabled=false`, `orders_placed=false`. This is a safe fail-closed integration smoke, not a strategy-performance claim.
- The original live checkout `/opt/hes-trade-agent` remains dirty with many pre-existing tracked/untracked files. It was not reset, cleaned, checked out over, or modified for code. The only operational side effect from the existing analysis script was its intended decision-snapshot output; collector data files were not edited manually.

### Exact candidate references

- PR #410 remains OPEN/Draft/unmerged. Head at this checkpoint: `1d17a273b2ddbbc43f7b84091d656f8734f83e95`; base `integration/gateio-persisted-feed-signal-agent-20261026` at `2e8d3859ef154b030e0965ad4479f3fad36ae4c0`; mergeable: `true`.
- Last code-bearing SHA with the five green PR workflows and local full suite is `daa7d9f1d48bc132e1c6a5c5c1558d2e0cf0b156`; documentation-only commits follow it. Full local suite: 628 passed + 19 subtests. Do not transfer that test claim to the later documentation head without rerunning exact-head CI.

### Next execution step

- Keep services untouched; add a deterministic, non-production fault-injection harness that proves process interruption → bounded reconnect → REST gap backfill → idempotent recovery, then run it against the same canonical adapter and record exact SHA/artifacts. Only after this can G3 advance. Do not simulate by killing production services.
- Release status remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. No PR merged, no production pointer changed, no exchange account connected, no order executed.


## Reconnect recovery integration-test checkpoint — 2026-11-02 (later update)

- Added `tests/collector/test_gateio_reconnect_recovery_integration.py` to exercise the actual collector loop through a simulated WebSocket transport disconnect, bounded reconnect, second REST sync, real atomic merge/persistence, and deduplication. The test writes only into pytest's temporary directory; it does not stop or modify the live collector services.
- Test-authoring caught and fixed a test isolation issue: `_append_new` has a definition-time default output path, so the integration test now explicitly injects its temporary output path. The initial test failure was test setup, not a collector regression; rerun after the fix passed.
- Exact code/test SHA: `9c6b1723272c69d2cdfabaf90efe22c5a794a388`.
- Exact SHA local validation: focused collector suite `18 passed in 0.21s`; full repository `629 passed, 19 subtests passed in 4.98s`.
- Five GitHub Actions workflows for this exact SHA were observed `in_progress` at checkpoint time; no green result is claimed until they finish. Earlier five-workflow green evidence applies only to `daa7d9f1d48bc132e1c6a5c5c1558d2e0cf0b156`.
- PR #410 head is now `9c6b1723272c69d2cdfabaf90efe22c5a794a388`, OPEN/Draft/unmerged, mergeable reported true. No merge or deployment performed.
- Scope limitation: the integration test proves deterministic reconnect + REST sync + atomic persistence in a controlled fake-transport scenario. It does not prove real network interruption/recovery, exchange-side continuity, deployed runtime parity, 24h WebSocket resilience, or strategy profitability. G3 remains PARTIAL/BLOCKED until live-safe evidence and remaining fault-injection checks are completed.
- No production service was stopped/restarted; no exchange account was connected; no order was placed. Release stays HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.


### CI status refresh for reconnect-test SHA `9c6b1723272c69d2cdfabaf90efe22c5a794a388`

- `Native OHLCV Dashboard Single Path v1`: completed / success.
- `Gate.io Public Candle Evidence Smoke v1`: completed / success.
- `Gate.io Dashboard Full Repository Regression`: in progress at last poll.
- `Native OHLCV Browser Render Smoke v1`: in progress at last poll.
- `Native OHLCV WebSocket Live Smoke v1`: in progress at last poll.
- The exact-SHA local suite is green, but CI is not yet fully green. Recheck these three in-progress runs before treating candidate validation as complete.


## Follow-up continuation checkpoint — exact CI and release-gate refresh (2026-11-02)

- Refreshed all five PR-triggered GitHub Actions for exact test SHA `9c6b1723272c69d2cdfabaf90efe22c5a794a388`: all five completed successfully: Native OHLCV Dashboard Single Path v1; Gate.io Public Candle Evidence Smoke v1; Native OHLCV Browser Render Smoke v1; Native OHLCV WebSocket Live Smoke v1; Gate.io Dashboard Full Repository Regression.
- Exact SHA local focused collector/recovery tests: `18 passed in 0.22s`; the same SHA previously passed full suite `629 passed, 19 subtests`. Docs-only checkpoint commits followed this code/test SHA; do not claim those workflows ran on the latest docs head.
- PR #410 is OPEN, Draft, unmerged; current branch head after checkpoint updates: `ae897412667460813ef002c3cd71b90367c6387b`; base branch `integration/gateio-persisted-feed-signal-agent-20261026`, base SHA `2e8d3859ef154b030e0965ad4479f3fad36ae4c0`, mergeable reported true. No merge was authorized or performed.
- Reconciled remaining release blockers from `docs/RELEASE_READINESS.md`: G0 lineage PARTIAL; G1 PARTIAL until final combined-stack exact SHA; G2 PASS for bounded Gate.io Spot scope; G3 PARTIAL (live WS/REST fault injection and authorized-runtime recovery/parity missing); G4 PARTIAL (deployed route/runtime parity missing); G5 BLOCKED (independent strategy/risk approval and sufficient forward OOS evidence missing); G6 BLOCKED/OFF (execution venue mapping/precision/minimums/idempotency/fill-status-fee reconciliation and separate authorization missing); G7 PARTIAL (runtime roots and rollback proof missing); G8 BLOCKED (final stack review/release artifacts/go-no-go missing).
- Do not repeat the prior 24h REST soak solely to duplicate evidence. Next safe technical step is an isolated, non-production, live-safe WS/REST outage harness with recorded source responses, then exact candidate stack reconciliation. Do not stop/restart production services as fault injection; runtime changes require authorization and must preserve the dirty live checkout.
- Release remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. No production service/pointer changed; no account connected; no live order placed. Delivery target remains 2026-11-19.


## PR dependency-stack diagnostic — 2026-11-02

- Refreshed candidate CI at PR #410 test SHA `9c6b1723272c69d2cdfabaf90efe22c5a794a388`: all five workflows now completed successfully (Dashboard Single Path, Gate.io Public Candle Evidence Smoke, Full Repository Regression, Browser Render Smoke, WebSocket Live Smoke). Local focused suite remains 18 passed; full suite on this SHA 629 passed + 19 subtests. Latest docs-only branch head is `65de7811dd9fd88634bfbc4768889ea6c4851353`; CI results are for the exact code/test SHA above, not the later checkpoint-only commit.
- PR ancestry snapshot: #408 head `cf2fad0c7363a33181bc94c3b2e4f6155d8b0a72` targets #406 head `9d761f0c7b140de52a3a7a1afc3f8e0ad7154927`; #406 targets #405 head `1871755507fc250198ea52985f426d1d66597c41`; #405 targets `consolidated/gateio-dashboard-signal-agent-v1` at `ee348e33111ebf6f9e4366ba3d211d46f44fadd7`. These PRs are open drafts; no merge performed. PR #408 exact-head CI was 4/4 success.
- Historical dependency diagnosis: PR #406 exact head's Full Repository Regression failed during pytest collection because three tests imported fixed absolute paths under `/opt/hes-trade-agent/scripts/` that are absent in a clean GitHub Actions checkout (`run_decision_report_24h_v1.py`, `run_matured_no_trade_validation_v1.py`, `run_no_trade_decision_audit_v1.py`). PR #408 descendant head passes full regression, so the issue is repaired in the descendant stack; do not rerun or duplicate that fix without rechecking current exact head. Keep path resolution repository-relative in new tests.
- PR #405 exact head had three failing candidate workflows (Full Repository Regression, Dashboard Single Path, Browser Render Smoke); descendant #406 fixed two of those, and descendant #408 has all four relevant workflows green. Preserve the stack ancestry and revalidate the exact final combined-stack SHA before release.
- This is a stack lineage/CI diagnostic only. It does not clear runtime WS/REST fault injection, deployed frontend parity, strategy/risk approval, forward OOS, execution mapping/authorization, backup/rollback, or final release gates. Disposition remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.
