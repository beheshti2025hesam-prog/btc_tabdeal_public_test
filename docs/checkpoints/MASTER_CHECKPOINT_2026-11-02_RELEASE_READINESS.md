# HES Trade Agent — Master Checkpoint: Release Readiness & Documentation

**Checkpoint date:** 2026-11-02 (UTC)  
**Target delivery:** 2026-11-19  
**Purpose:** resume from the current evidence and release state without rediscovery, duplicate implementation, or denominator drift.

> **Project memory contract:** Memory = project map/context; GitHub = technical truth; Chat = conversation log.  
> **Release disposition:** Dashboard/frontend integration is merged and deployed as an immutable read-only release on the sole VPS. Trading remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY; no account connection, execution enablement, or live orders are authorized.

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


## Read-only live Gate.io collector smoke — 2026-11-02 07:15 UTC

- Executed the candidate collector entrypoint from isolated checkout `/tmp/hes-pr410-gateio-collector-20261102` with `HES_GLOBAL_CANDLES_OUTPUT=/tmp/hes_gateio_isolated_live_smoke_20261102.jsonl` and 35-second bounded timeout. This used public Gate.io market data only; no credentials/trading endpoints, and did not touch any production systemd service or canonical live candle file.
- Live collector log: `HES_GLOBAL_MARKET_START source=gateio_public_spot symbol=BTC_USDT timeframe=15m last_ts=-1`; fetched and persisted 499 closed candles; `HES_GLOBAL_MARKET_WS_SUBSCRIBED`; received termination signal and logged `HES_GLOBAL_MARKET_STOP`. Timeout returned shell code 124 by design after 35 seconds; collector handled TERM and emitted its stop marker.
- Temp-file audit: 499 rows; all closed; unique timestamps; every adjacent open_time delta exactly 900 seconds; source `gateio_public_spot`, symbol `BTC_USDT`, timeframe `15m` on every row. No duplicates/gaps/identity drift in this isolated snapshot.
- Separate direct read-only REST+WS smoke at 2026-11-02 07:16 UTC: canonical `GateioSpotKlineSource` fetched 2 closed candles with zero gaps; Gate.io WS accepted `spot.candlesticks` subscription for `15m_BTC_USDT` and delivered 2 updates with required candle fields; no WS errors. This confirms basic real endpoint reachability and subscription, not an induced outage/recovery cycle.
- This materially advances G3 evidence from deterministic test to short real-endpoint collector run, but **does not** prove WS recovery after real interruption, long-duration soak on the candidate code, or deployed candidate runtime parity. Keep G3 PARTIAL. Do not rerun the historical 24h REST soak just to duplicate existing evidence; next targeted proof is controlled, isolated reconnect/backfill after actual socket interruption, then runtime-lineage/soak under authorized change control.
- Exact code/test SHA remains `9c6b1723272c69d2cdfabaf90efe22c5a794a388` with all 5 PR workflows green and local suite 629 passed + 19 subtests. Docs-only commits after it are not covered by that code SHA's CI.
- Release remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY; no production service/pointer changed; no account connected; no order executed.


## Controlled real-socket reconnect + REST backfill proof — 2026-11-02 07:17 UTC

- In an isolated candidate checkout, opened a real Gate.io public WebSocket, subscribed to `spot.candlesticks` / `15m_BTC_USDT`, received one valid update, deliberately closed the socket, then opened a fresh socket and received another valid update. Both subscriptions succeeded with no WS errors.
- After reconnect, fetched the canonical native REST adapter batch (`GateioSpotKlineSource.fetch(symbol='BTCUSDT', interval='15m', limit=5)`); 4 closed candles returned with zero adapter-reported gaps. Persisted only to `/tmp/hes_gateio_live_reconnect_backfill_20261102.jsonl` via the existing atomic merge helper, then replayed the identical batch. The second merge did not duplicate rows.
- Result: 4 persisted closed rows; unique timestamps; contiguous 900-second spacing; all source/symbol/timeframe identities correct; repeat merge retained the same last open time. Exact test window 2026-11-02T07:17:28Z–07:17:36Z. No credentials, no trading endpoints, no production file/service changes.
- Interpretation: this is real-endpoint socket close + fresh-subscription + REST reconciliation/idempotency evidence, paired with the automated collector-loop reconnect test. It does not force the collector process itself to experience a network exception while live, prove prolonged stability, or prove deployed candidate runtime parity. G3 remains PARTIAL pending authorized runtime lineage/soak and broader failure modes.
- Release remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. No PR merge, deployment, service restart, account connection or order execution.


## Isolated collector process-restart + real REST gap repair — 2026-11-02 07:18 UTC

- Ran the candidate collector process twice in an isolated checkout with output redirected to `/tmp/hes_gateio_process_restart_backfill_20261102.jsonl`; each run was bounded to 8 seconds and terminated by SIGTERM. Both runs logged START, WS_SUBSCRIBED and STOP. No production service or data file was touched.
- First run fetched 499 contiguous closed Gate.io Spot BTC_USDT 15m candles and subscribed to the real WebSocket. In the temp file only, deliberately removed one recent candle to inject a single 900-second gap (498 rows remained).
- Second fresh collector process started from the persisted last timestamp, fetched canonical REST history, repaired exactly one missing recent candle (`added=1 backfilled=1`), subscribed to WS and stopped cleanly. Final temp-file audit: 499 rows, all closed, unique, contiguous at 900-second intervals, correct source/symbol/timeframe identity.
- This is the strongest bounded recovery evidence so far: actual candidate collector process restart + injected persisted gap + live REST repair + real WS subscription, all isolated from production. Combined with real socket close/reconnect and the automated collector-loop disconnect test, it materially supports G3, but does not replace longer-duration resilience/soak, deployed candidate runtime parity, other failure modes, or explicit authorized production change control. Keep G3 PARTIAL, not PASS.
- CI still applies to code/test SHA `9c6b1723272c69d2cdfabaf90efe22c5a794a388` (5/5 workflows green; local 629 passed + 19 subtests); later branch commits are documentation-only. Release remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.


## Production runtime lineage comparison — 2026-11-02 07:19 UTC

- Read-only inspection confirms all three existing services remain active/running and use `/opt/hes-trade-agent/.venv/bin/python -u /opt/hes-trade-agent/scripts/run_global_market_data_gateio_service.py`; security/sandbox drop-ins are present. No service restart/reload/stop was performed.
- Live checkout `/opt/hes-trade-agent` is on branch `feat/gateio-global-market-data-v1`, HEAD `060d0d36ae6140a03d9a74495bb3899637ed3827`, with extensive pre-existing tracked and untracked modifications. Do not reset, clean, checkout over, or overwrite it.
- Runtime/candidate SHA-256 hashes differ: live `forward/global_market_data_gateio_v1.py` = `128f4af844d6ad477568bb82706ee5d00f3701004cc81479f71ff04cad87c06f`; candidate = `f7b6edeb1874ee390912780d7777c9decd56fe658939889e9590864e63a61786`. Live wrapper = `280992fe64c1a2d4d97ded6992a5f0ab9b275e7ce440872891ebf4a45bf76919`; candidate wrapper = `87ff152a6cf74a762fe21fa57fec43b04d40af7a7c7841155f0f5184bc9a90a3`. Runtime parity is therefore NOT proven; do not deploy by copying candidate files into this dirty checkout.
- Safe next operation is a file-by-file, non-mutating diff and explicit release-stack reconciliation to establish the smallest authorized migration/rollback plan. Any installation/restart needs an explicit change window/authorization and backup/rollback evidence. G7/G4 remain PARTIAL; G3 remains PARTIAL; release HOLD.


### Installed systemd template parity check — 2026-11-02

- Compared all three candidate unit templates (`15m`, `1h`, `4h`) against the installed unit files on the single VPS: all three match byte-for-byte.
- Compared both `20-hes-security-umask.conf` and `30-hes-sandbox.conf` drop-ins for all three services: all six installed drop-ins match their versioned candidate files byte-for-byte.
- This closes the unit-file text-parity question, but not collector-code parity: live runtime collector/wrapper SHA-256 differs from candidate (recorded above). No unit reload, restart, install, or production code change was performed.

### Minimum safe migration plan (not executed)

1. Resolve/review the final PR dependency stack and exact combined SHA; require exact-SHA CI and independent review.
2. Before any live code change, capture a read-only snapshot of the dirty checkout, tracked/untracked inventory, current `current` pointer target, active unit/drop-in hashes, current data-file hashes/row counts, and service health. Do not use `git reset`, `git clean`, branch checkout, or overwrite the existing checkout.
3. Build a separate versioned release directory/checkout; validate venv/dependencies and all tests there. Stage new collector code and canonical adapter without touching the active checkout.
4. Prepare an explicit backup and tested rollback script; validate syntax and filesystem ownership/permissions under `sentinelx` and existing systemd sandbox restrictions.
5. Only during an explicitly authorized change window: switch service WorkingDirectory/ExecStart or atomically switch a release pointer; restart one service at a time; verify candle freshness, no gaps/duplicates, WS subscription, REST backfill, service health, and frontend/analysis same-batch parity; roll back immediately on any failed gate.
6. Keep all trading execution disabled. No account/venue order adapter changes until independent G5/G6 approvals and explicit authorization.

This plan is documentation only; it does not authorize or perform a deployment.


### Latest documentation-head local verification — 2026-11-02

- After the above checkpoint/release-doc updates, checked out exact branch head `b20805e309a3240aeed6e65e5da85a43063f5415` in the isolated candidate checkout and reran the complete repository suite: **629 passed, 19 subtests passed in 5.00s**. `compileall` for the Gate.io collector, service wrapper and 24h soak script also passed.
- The five GitHub Actions are green on code/test SHA `9c6b1723272c69d2cdfabaf90efe22c5a794a388`; later changes up to `b20805e...` are documentation-only, and local full-suite verification now also covers `b20805e...`. No claim that CI workflows ran on this documentation-only head.


## UX review and accessibility optimization — 2026-11-02

### Existing product surface reviewed
- Reused the existing dashboard and its current Market, Strategy V2, Mother, News Radar, Safety, and Journal panels. No parallel frontend, dashboard, chart, journal, or data engine was created.
- Existing Gate.io chart and analysis single-path boundary remains unchanged: Gate.io Public Spot BTC_USDT → persisted `global_market_data_reader_v1` → existing feature/specialist projections. The browser does not fetch exchange candles directly.
- Existing read-only API boundary and execution-off state remain unchanged. No order controls or write routes were introduced.

### UX gaps addressed in the existing dashboard
- Added keyboard-accessible skip navigation and a sticky, horizontally scrollable section navigator for the six existing panels.
- Corrected heading hierarchy and gave each section a stable anchor and accessible label.
- Added polite live announcements for changing market/evidence/journal status.
- Added a screen-reader table caption and scoped journal column headers.
- Added visible keyboard focus styles, mobile-friendly navigation overflow, and reduced-motion-aware scrolling.
- Kept the existing English default, dark visual system, pinned local chart library, and existing API/data architecture. No new runtime dependency.

### Exact-head evidence — PR #411
- PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/411
- Candidate head: `0b7722a23bbad428056c706101f54e7bc13cc33b`; based on PR #408 head `cf2fad0c7363a33181bc94c3b2e4f6155d8b0a72`.
- Full repository regression: **792 passed, 70 subtests passed** — run https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41406455450.
- Dashboard/native single-path regression: **PASS** — run https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41406455359.
- Browser render/responsive smoke: **PASS** — run https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41406455515.
- Browser artifact ZIP SHA-256: `1db83fe010ad002805571247570f8b0c3afaf1ca9f6935cc0aed8089d7a849c5`.
- PR #411 is OPEN/Draft/unmerged; it is stacked on #408. Do not merge it independently or bypass #398 → #405 → #406 → #408.

### Remaining UX/release acceptance
- The automated candidate render is not deployed-runtime proof. G4 remains PARTIAL until the complete PR stack is reconciled and the deployed dashboard routes are verified against the approved release SHA.
- Manual keyboard/screen-reader acceptance has not been performed; automated semantic/DOM and browser checks are the evidence currently available.
- No language toggle was added: the existing application default remains English, and no new product-language requirement was approved in this UX task.
- No deployment, service restart, production pointer change, account connection, or order execution occurred. Keep HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.
- Delivery target remains **2026-11-19**; protect the **2026-11-04 chart acceptance milestone** and prioritize final stack/runtime reconciliation over further visual redesign.


### Dashboard stack integration note — important
- PR #411 is a UI-only child of PR #408. PR #410 is a separate Gate.io/Signal Agent candidate and also changes `web/dashboard.py`; therefore #411's successful tests do not prove that the #408 Mother/News dashboard and #410 Gate.io/Signal Agent changes have already been combined.
- During final stack reconciliation, preserve the six-panel navigation/accessibility improvements while integrating the existing backend/API changes. Reuse one dashboard entrypoint and one chart path; do not keep competing dashboard implementations.
- Re-run exact-final-SHA full regression, dashboard single-path, browser render and responsive checks after the combined stack is assembled. Until then G4 remains PARTIAL and PR #411 remains Draft/unmerged.


## Exchange sequence semantics hardening — 2026-11-02

### Existing implementation reused
- Reviewed supplied research file `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md` against existing PR #402; no second registry or sequence engine was created.
- PR #402 already adds the exact-scope capability registry and fail-closed legacy Tabdeal observation boundary. Its 17 registry entries keep unsupported/unpinned semantics disabled; Gate.io candle open time is explicitly treated as a candle bucket key, not a trade sequence.
- Active HES market-data architecture remains Gate.io persisted closed-OHLCV for chart/candles/indicators. This sequence-registry work does not replace or duplicate that feed, nor does it connect directly to order execution.

### Code-review defect found and corrected on existing PR #402
- Defect: a registry record could state `semantic_class=ORDERED_EVENT_SEQUENCE` and `claims.ordered=true` while explicitly setting `capabilities.ordered_event_sequence=false`. The old resolver derived runtime permission from the claim, not the capability flag.
- Fix: VERIFIED ordered records now require the explicit ordered capability and the resolver reads the capability flag. Added a negative regression test for the contradictory record.
- Commits on PR #402 branch: `49903050b04f0acbe14574b66aa96281f3c456c4`, `a04c0139d58ea096c97131e8286a884481cdf2df`, `a49bfa8d87964b247c47b4090d827f47bfe4899c`.
- First exact-head workflow exposed an expected fixture mismatch: the synthetic-only verified test registry did not declare the now-required capability. Updated the fixture to explicitly grant `ordered_event_sequence=true`; no production registry capability was enabled by this fixture change.
- PR #412 was closed as superseded; the two code/test changes were applied directly to PR #402 to preserve the existing main-targeted CI path and avoid a duplicate stacked PR.

### Current evidence / release boundary
- PR #402: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/402; remains OPEN/Draft/HOLD and unmerged.
- Current PR head after fixture correction: `a49bfa8d87964b247c47b4090d827f47bfe4899c`.
- Exact-head GitHub Actions were triggered for that SHA; at checkpoint update, focused Controlled Forward Runner, Clean Forward Evidence, Forward Integration, and collector persistence workflows were still running. The preceding exact-head attempt failed in two test modules at collection because of the synthetic fixture mismatch; this is corrected in the latest head and must be rechecked before claiming pass.
- Earlier PR #402 head `50b6b3593714c163d1bba4d9a18a12cfab83adc4` had successful Controlled Forward Runner, Clean Forward Evidence, Forward Integration, Local Durable Collector and Collector Persistence workflows, but those results do not substitute for the latest SHA.
- Registry source hashes/review pins are still incomplete; Tabdeal trade.sequence remains UNKNOWN. No live collector, exchange credentials, VPS changes, account access, order, or execution enablement.
- Keep HOLD / NO_TRADE_ONLY for the legacy Tabdeal sequence path. This is a code hardening candidate, not evidence to activate it.

### Delivery
- Delivery target remains **2026-11-19**; preserve the **2026-11-04 chart acceptance milestone**. Do not let this bounded legacy-protocol hardening displace Gate.io chart acceptance or final frontend/backend stack reconciliation.


### Exact-head CI closure — 2026-11-02
- Corrected PR #402 head `a49bfa8d87964b247c47b4090d827f47bfe4899c`: **26/26 GitHub Actions workflow runs completed successfully**.
- Critical exact-head evidence:
  - Controlled Forward Observation Runner: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407726023
  - Clean Forward Evidence Verification: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407726070
  - Forward Integration Verification: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407725993
  - Collector Persistence Hardening: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407726013
  - Local Durable Collector Safety: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407726124
  - Identity Integrity: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407726141
  - Actions Execution Canary: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41407725992
- The first run's fixture collection failure is superseded by the corrected exact-head results above. The fixture now explicitly sets its synthetic-only ordered capability; the production registry remains unchanged and all real exchange capabilities remain disabled/unpinned.
- PR #402 remains OPEN/Draft/unmerged. Green CI verifies the tested code, not missing source hashes, independent human review, VPS regression, runtime activation, or permission to execute. Maintain HOLD / NO_TRADE_ONLY for the legacy Tabdeal path.


## Canonical integration consolidation — 2026-11-02 (11:16+03:30)

### UX integrated into Mother/Strategy/News candidate
- PR #411 was not merged separately. Its three changes were applied directly to PR #408's main-targeted branch `feat/mother-v2-orchestration-rebased-20261101`, avoiding a parallel dashboard branch.
- Integrated files: `web/dashboard.py`, `web/static/dashboard.css`, `tests/test_dashboard_routes_v1.py`.
- Preserved skip link, semantic main landmark, H1, six-section navigation (Market/Strategy/Mother/News/Safety/Journal), live status announcements, accessible journal caption, keyboard focus indicators, responsive nav, and reduced-motion-aware scrolling.
- Commits: `02abb1a454d933487c4d14061b9982b6e0177d0a`, `0bb37b98fcb085dd23a22c57ff82c0c8089e42ea`, final exact tested head `b408a89e169bd8b778341c3d8e161def7d4a6b8a`.
- PR #411 was closed as superseded by this direct consolidation. No UX functionality was discarded and no new runtime dependency was introduced.

### Exact-head CI for consolidated candidate
- PR #408 remains OPEN/Draft/HOLD, target `main`, mergeable.
- Exact head `b408a89e169bd8b778341c3d8e161def7d4a6b8a`: **30/30 GitHub Actions workflow runs succeeded**.
- Includes Signal Agent regression, Gate.io dashboard full repository regression, Native OHLCV dashboard single path, Native OHLCV browser render, Forward Integration Verification, Clean Forward Evidence, Controlled Forward Observation, Collector Persistence, Source Identity Reconciliation, Actions Execution Canary, and all feature/risk/backtest suites.
- These CI results validate code at this exact SHA; they do not prove VPS deployment/runtime state, 24-hour live collector continuity, external independent approval, or permit real orders.

### PR #410 reconciliation decision
- PR #410 (`fix/gateio-signal-strategy-wiring-20261029`) remains a legacy integration branch based on `integration/gateio-persisted-feed-signal-agent-20261026`, not on current `main`.
- Its head is `95abd96f1823c9ac83a813b19e56d250f6bca1ff`; comparison with current main reports 211 commits ahead / 30 behind and a divergent merge base. Its changed-file set includes the historical dashboard, Signal Agent, Native OHLCV and strategy tree in addition to the new collector/service artifacts.
- Do NOT retarget or merge PR #410 wholesale: this would reintroduce overlapping dashboard/data/strategy history and duplicate older implementation paths.
- The existing `forward/native_ohlcv_v1.py` and `forward/native_ohlcv_gateio_v1.py` are already present on main. PR #410's additional `forward/global_market_data_gateio_v1.py` background collector and separate `global_market_candles*.jsonl` outputs are absent from main. Its service units and public candle smoke workflow are also absent. This is a distinct collector/service path and must be proven necessary and reconciled with the canonical existing native OHLCV pipeline before any selective port. Do not introduce a second source or persisted candle pipeline.
- PR #410's existing five workflows passed on its old exact head, but they do not validate a port into the current canonical stack. A selective code-only port of its non-duplicative Gate.io collector/service assets is now present in PR #408; see the new integration addendum below. No service has been installed or activated.

### Architecture and safety boundaries
- Gate.io Public Spot remains the sole authoritative market-data source for chart/candles/indicators. Use the existing native OHLCV adapter/reader as canonical; no browser exchange fetch or parallel chart/indicator engine.
- Exchange adapter remains execution-only. Execution OFF / NO_TRADE_ONLY. No live orders, credentials, VPS service changes, daemon reloads, deploys, or account actions.
- PR #408 is the current consolidated code candidate for Strategy V2 + News Radar + Mother + accessible UX. PR #398 remains merged to main.
- PR #410 remains HOLD pending a narrow architecture decision: either prove its separate collector is required and adapt it to the canonical reader, or retire its duplicate collector/service path and retain only non-duplicative evidence/workflows.
- Team remains project owner + ChatGPT; do not claim independent human approval.

### Delivery
- Fixed target remains **2026-11-19**.
- Preserve **2026-11-04 chart acceptance** as the next critical milestone. Finish the PR #410 collector decision and exact-head runtime/read-only acceptance without delaying chart acceptance.
- If mandatory runtime or safety gates remain open at delivery, ship only the verified read-only/paper scope.


## Gate.io persisted collector + source-contract integration addendum — 2026-11-02

### Canonical producer/consumer wiring
- Main-targeted PR #408 now selectively includes the missing persistent producer for the existing `global_market_data_reader_v1` contract.
- Reuses the main-branch `GateioSpotKlineSource` adapter. One persistent collector writes the exact three shared JSONL paths consumed by the existing dashboard/analysis reader: 15m `global_market_candles_v1.jsonl`, 1h `global_market_candles_1h_v1.jsonl`, 4h `global_market_candles_4h_v1.jsonl`.
- WebSocket is a wake-up channel only; persisted OHLCV is re-fetched via the shared REST adapter. Base and quote volume remain separate; trade count/taker-buy flow remain unavailable.
- Selectively ported: `forward/global_market_data_gateio_v1.py`, its reconnect/persistence tests, service entry point, 15m/1h/4h systemd templates and sandbox drop-ins, optional 24h read-only soak, Gate.io public candle contract smoke workflow, README/service documentation, and optional pinned WebSocket client dependency. Existing `native_ohlcv_v1.py`, `native_ohlcv_gateio_v1.py`, reader, dashboard and feature pipeline were not replaced.
- Gate.io adapter hardened in place: requires exactly eight documented Spot candle fields and validates the eighth closed-window flag; records with false flag are excluded even if their timestamp appears closed. Adds explicit `gateio_spot_candlestick_v2` contract constant.
- Strategy evidence provider hardened in place: Gate.io accepts only the documented Spot candle endpoints and rejects fabricated trade-count/taker-buy fields. No Binance support from the legacy branch was copied.
- Dashboard and optional soak now read from `HES_GLOBAL_MARKET_DATA_ROOT`; staged dashboard/soak units set it to `/opt/hes-trade-agent`, matching collector outputs under `/opt/hes-trade-agent/data/forward`. This avoids reading candle files from an immutable release directory. Added a regression test and documented the deployment path contract.

### Exact-head status
- Latest candidate branch remains PR #408, target `main`, Draft/HOLD.
- The source-contract hardening commit `43e674185c03dcacc6f15b5f1c3fb7999b1d7501` first exposed four Signal Agent regression fixture failures because old synthetic Gate.io batches used the generic `klines` endpoint label and fabricated trade/taker fields. The production guard was retained; the fixture was corrected to use `spot_candlesticks` and unknown flow values in commit `6192f16e98deb646b72d5d64058dae4de08b0bbd`.
- PR #411 was closed as superseded after its three UX files were integrated directly into PR #408.
- PR #410 has not been merged wholesale; its branch remains a historical source. Do not merge or retarget it. After PR #408 exact-head checks pass, close PR #410 as superseded and retain only the selective, tested changes in PR #408.

### Runtime boundary
- These are code and systemd templates only. No unit installed, daemon-reloaded, enabled, started, restarted or stopped; no 24-hour soak run; no VPS changes; no order execution. Keep execution OFF / NO_TRADE_ONLY.
- Before any live feed service activation, require explicit owner approval, exact release SHA, staged unit/security validation, and controlled read-only soak. Delivery target remains 2026-11-19; chart acceptance milestone remains 2026-11-04.


## Final exact-code validation — 2026-11-02

- Canonical integration PR #408 latest code SHA: `6192f16e98deb646b72d5d64058dae4de08b0bbd`, target `main`, remains Draft/HOLD and unmerged.
- Exact SHA checks: **30/30 succeeded**. Full repository pytest suite: **816 passed, 70 subtests passed**.
- Specific passing evidence includes: Gate.io public candle contract smoke; Signal Agent + Existing Gate regression; Native OHLCV Dashboard Single Path; Native OHLCV Browser Render; Forward Integration Verification; Signed Source Evidence Contract; Controlled Forward Observation; Clean Forward Evidence Verification; Local Durable Collector; Capital Risk Boundary; and Actions Execution Canary.
- The four Signal Agent test failures on prior SHA `3658f5ac5bfe6306e3d9b02304ad6ee03843357d` were test-fixture mismatches, not a reason to weaken the Gate.io endpoint/unknown-flow guard. The corrected fixture uses the documented endpoint and unavailable fields remain `None`; the exact final SHA passed.
- Dashboard service now `Wants=` and `After=` the 15m, 1h and 4h canonical Gate.io collector units. The shared data root is explicit and read-only to the dashboard.
- PR #410 has been closed as superseded after selective, non-duplicative collector/service/source-contract changes were ported into PR #408. Its stale dashboard/strategy history and its legacy Binance support were not copied. PR #411 remains closed as superseded after UX changes were folded into #408.
- No VPS service install, daemon reload, enable/start/restart, 24h soak, deployment, credential access, account access or order execution occurred. Keep all runtime actions pending explicit owner approval and release gates.
- Current release target remains **2026-11-19**; chart acceptance remains **2026-11-04**. The current PR is a validated code candidate, not a deployed production release.


## Superseding final update — integrated dashboard/frontend deployment — 2026-11-02 16:12 UTC

This section supersedes earlier candidate-only statements in this checkpoint about PR #408 remaining Draft/unmerged and the dashboard not yet being deployed. Historical evidence above remains historical.

### Consolidation and repository state
- Canonical PR #408 was marked ready after the owner-directed completion request and the project-pair technical audit, then merged to `main` as **`388d4aa326ce4e678f63400f7ad4b53ae76b7b20`**.
- Exact tested candidate head immediately before merge: `47adc610f70452c9ea23c1d2fd939013563466e5`; merged commit tree is identical: `e9d0d8097b87d1e4e4348c6665683e3416c64f2c`.
- Exact candidate Actions: **32/32 succeeded**. Full repository regression: **817 passed, 70 subtests passed**. A clean detached clone on the VPS independently reproduced **817 passed, 70 subtests passed**. `systemd-analyze verify` accepted the dashboard and all three Gate.io unit templates; only an unrelated pre-existing Xray warning was emitted.
- Browser render on the exact candidate tree: PASS; 239 closed candles; chart/API/all-candle batch parity; displayed close and volume match source; no direct browser exchange request or external chart CDN; responsive widths 390/768/1440 with no horizontal overflow. Artifact ZIP SHA-256: `20408c4894f520b136662e5543aa897be2b49588dc4799bcb5ea05c00de8d94a`.
- Gate.io public candle contract smoke: PASS for 15m and 4h; documented eight-field Spot schema and closed-window flag verified; continuity PASS; trade count and taker-buy flow remain UNKNOWN/not provided. Artifact ZIP SHA-256: `bbccdab8f9087b93459c90bb9d4d7ed64da41cedb9660f610e254e0d0e1d02e3`.
- PRs #405, #406 and #407 were closed as superseded by the merged consolidated PR #408. PRs #410 and #411 remain superseded/closed; no duplicate dashboard or candle path was retained.

### Immutable VPS release and rollback lineage
- The single VPS now runs immutable release: `/opt/hes-trade-agent/releases/388d4aa326ce4e678f63400f7ad4b53ae76b7b20`.
- Archive SHA-256: `6f77f27ae288572058f9a13b6a72897ed8349b0ccaaccb0b521ebb702c30c37e`.
- `/opt/hes-trade-agent/current` was switched atomically from previous release `/opt/hes-trade-agent/releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0` to the new immutable release.
- Before switching, the exact previous dashboard unit and existing drop-ins were preserved under `/opt/hes-trade-agent/releases/rollback-dashboard-before-388d4aa326ce/`.
- Installed the exact repository dashboard systemd unit plus `30-hes-news-monitor-state.conf`; explicit shared paths are configured for the Strategy V2 report, canonical journal, Gate.io market-data root and News Radar snapshot. `StateDirectory=hes-news-monitor` provisions only the News Radar writable state directory.
- Daemon reload and controlled dashboard restart succeeded. `hes-readonly-dashboard.service` is ACTIVE, runs as `sentinelx:sentinelx`, binds only `127.0.0.1:8765`, has `ProtectSystem=strict`, `NoNewPrivileges=yes`, `ReadOnlyPaths=/opt/hes-trade-agent/releases /opt/hes-trade-agent/data/forward`, and **no ReadWritePaths exception**.
- Existing 15m/1h/4h Gate.io feed services remained active; no feed service was duplicated or restarted by the dashboard.

### Deployed runtime acceptance
- Actual deployed runtime returned HTTP 200 for `/`, all dashboard static assets and pinned Lightweight Charts, `/healthz`, `/api/candles` for 15m/1h/4h, `/api/strategy-v2`, `/api/mother`, `/api/news`, and `/api/journal`.
- All three candle intervals returned 240 candles from `gateio_public_spot` through `global_market_data_reader_v1`, with zero reported gaps. Symbol mapping is verified for the market-data symbol; execution-instrument mapping remains unverified.
- Strategy V2 projection: `VERIFIED / NO_TRADE`. Mother: `BLOCKED_GATE / NO_TRADE` with `NO_VALID_CANDIDATE`; independent audit witness verified. This is the intended fail-closed outcome, not a defect to bypass.
- News Radar: `OK`; current profile explicitly reports partial official macro/regulatory/central-bank and venue-announcement coverage. Runtime poll showed 6 sources OK, 1 OK-empty, 0 failed. No qualified domestic/Iran-equities source is enabled; do not imply domestic coverage or a comprehensive crypto-native newswire.
- Journal projection: `VERIFIED`, 717 records. POST to `/api/journal` returned 405. CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy and no-store headers were verified.
- A 285.6-second read-only runtime soak sampled 15 times. Every health, 15m/1h/4h candle, Strategy V2, Mother, News and Journal request returned HTTP 200; the service remained active; all candle batches remained gap-free; News Monitor completed two polls (16:05:01Z and 16:10:01Z); the canonical journal SHA-256 remained unchanged at `c0b6d18471596921f775091b886ee48d5e87a809aa9e3fe007cdbdeafa1fb004`.
- The original dirty checkout at `/opt/hes-trade-agent` was not cleaned, reset, checked out over, or overwritten. Its pre-existing modifications/untracked files remain preserved.

### Final scope and remaining independent gates
- **Integrated dashboard/frontend section: deployed and runtime-accepted for read-only/paper scope.** No parallel app, chart, feed, strategy, journal or indicator engine was created.
- Overall trading remains `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`. No account connection, exchange orders or execution enablement occurred.
- This frontend release does not prove the requested >90% paper win rate or the ≤3 high-quality signals/day target. Strategy/structure/confirmation quality, independent risk approval, execution-instrument mapping and adequate forward-only paper observations remain separate gates.
- News coverage remains deliberately partial and clearly labelled; unqualified sources remain disabled.
- Fixed milestones remain chart acceptance **2026-11-04** and delivery **2026-11-19**. Preserve the rollback release and do not modify the sole dirty checkout.


## Multi-market, multi-venue, multi-symbol, broker and News Radar audit — 2026-11-03

**Status: PARTIAL / NOT RELEASE-COMPLETE.** This is a read-only checkpoint update. No production files, services, release pointer, credentials, accounts or execution settings were changed.

### Live VPS verification
- SentinelX reports exactly one connected operational host (plan limit 1); there is no second VPS. The host-reported hostname is `vps-second-261930`, which is only a hostname label.
- `/opt/hes-trade-agent/current` resolves to immutable release `57ae4e659bec9eabf4f84991d8cffc041eb582c7`.
- Read-only dashboard, Gate.io 15m/1h/4h feed services, paper evaluator and learning loop were ACTIVE during this audit. No service was restarted or modified.
- The working checkout `/opt/hes-trade-agent` is on `feat/gateio-global-market-data-v1` with extensive tracked modifications and untracked candidate artifacts. Preserve it exactly: no clean/reset/checkout/overwrite. This working tree must not be mistaken for the immutable release.

### Existing implementation and candidate status
- **Canonical analysis data:** Gate.io Public Spot remains the sole authoritative crypto market-data source for candles, charts and indicators through the existing collector, `global_market_data_reader_v1`, Native OHLCV contracts and persisted feed. No second candle/indicator engine or analysis source.
- **Crypto symbols — PR #400:** existing Gate.io multi-symbol candidate covers BTC/ETH/SOL in isolated paths and chart selectors. Recorded probes returned 219 closed candles per symbol across 15m/1h/4h with zero gaps in nine samples. PR remains Draft/unmerged/non-mergeable; ETH/SOL are observation-only, not strategy-approved. Their service instances are staged, not active.
- **Other markets:** FX, US equities, Iran equities and commodities remain disabled/unqualified pending provider/entitlement, market calendar, adjustment and volume semantics, symbol master, freshness/health and evidence contracts. Do not claim multi-market readiness.
- **Execution venues/brokers — PR #401:** generic typed `ExecutionAdapterV1`, fail-closed preflight and durable idempotency/lifecycle journal exist as a candidate. No concrete authenticated venue adapter is approved. Gate.io data source does not choose or authorize execution venue; historical Tabdeal symbol mapping is insufficient.
- **Sequence safety — PR #402:** capability-driven exact-scope registry candidate exists; reported exact-head CI was 26/26. Capabilities remain disabled where source hashes/review pins are incomplete; Tabdeal unknown semantics remain unknown. Do not generalize sequence assumptions.
- **News Radar:** existing Brain, source registry, Gate.io announcements, five-minute monitor, durable digest-validated snapshot and read-only panel are deployed. Coverage remains partial official macro/regulatory/central-bank plus Gate.io venue announcements; no qualified Iran/domestic source or complete crypto-native wire is enabled.
- **Fed calendar — PR #423:** candidate adds Fed statistical releases and FOMC dates; recorded live probe was 2/2 sources OK with 22 events. BLS CPI/jobs calendar returned HTTP 403 and is excluded. Fed events remain unrated/context-only; no directional signal or veto. PR is open/unmerged and needs exact-head checks before promotion.
- **Precision-entry acceptance — PRs #424–#428:** 15m remains setup authority; 1m is advisory entry timing only. PR #428 reports 621 local tests passed, while exact-head GitHub checks were pending in its description. Its official precision ledger was reported absent. Therefore the >90% target is **NOT MET**.

### Remaining maturity gates
1. Keep BTC the only strategy-approved symbol. ETH/SOL observation-only until independent per-symbol soak, isolation and review pass. Keep FX/equities/commodities disabled until each profile is qualified.
2. Prove no cross-symbol/product contamination across candles, volume, indicators, caches, setup contexts, journals and outcomes; freshness/gap/health must be independent per symbol.
3. Retain the generic execution interface. A concrete adapter needs selected venue/product, official filters and units, idempotency, authenticated order/query/cancel/open-order/position/account reconciliation, fees/partial fills, protective/reduce-only semantics, source hashes, independent review, paper soak and explicit owner approval. No credentials or orders now.
4. News monitor must expose content freshness separately from transport health (fresh/stale/empty/failed and newest-publication age). Qualify sources only after terms, ownership, schema, freshness and VPS checks.
5. Any future News-to-Strategy integration must be a separately versioned **veto-only** gate with provenance, journal attribution, replay/negative tests and stale/corrupt fail-closed behavior. News must never create or strengthen a directional signal; partial coverage alone must not cause blanket veto.
6. Three signals/day is a hard cap, never a quota. Strict >90% must be measured on at least 100 resolved, uniquely linked, eligible 1m precision paper outcomes, with verified fees/slippage and independent OOS evidence. Exclude research/preapproval/unresolved/ambiguous records. Report net expectancy, profit factor, drawdown, and LONG/SHORT/regime splits. This is an acceptance criterion, not a guarantee of market outcomes.

### Delivery protection
- Do not merge PRs #400/#401/#402/#423/#428 independently based on descriptions or historical workflow counts; verify ancestry and exact final SHA, full regression, browser/runtime evidence and independent review.
- Protect **2026-11-04 chart acceptance** first; freeze optional market expansion until accepted. Freeze product scope 2026-11-12; final combined validation and rollback preparation 2026-11-13 to 2026-11-18; deliver only passed scope on **2026-11-19**.
- Preserve `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`. No live execution.

