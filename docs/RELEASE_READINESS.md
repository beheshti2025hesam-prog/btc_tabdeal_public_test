# HES Trade Agent — Release Readiness & Delivery Control

**Updated:** 2026-11-02 (UTC)  
**Target delivery:** **2026-11-19**  
**Disposition:** **HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY**  
**Canonical repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`  
**Latest project checkpoint:** [MASTER_CHECKPOINT_2026-11-02_RELEASE_READINESS.md](checkpoints/MASTER_CHECKPOINT_2026-11-02_RELEASE_READINESS.md)

## 1. Purpose and source of truth

This is the release-control contract for the existing HES Trade Agent. It is not a second implementation plan or replacement application. Inspect the repository, existing PR dependency stack, workflows, tests and checkpoints before changing code. Reuse or narrowly optimize existing components.

- GitHub commits, exact-head CI, artifacts and hashes are technical truth.
- The dated Master Checkpoint is the concise project map and current decision record.
- Chat is discussion history, not evidence that code, tests, deployment or runtime actions occurred.
- Exactly one VPS exists. Do not invent or plan for a second.
- The target date is fixed at **2026-11-19**. Schedule pressure never waives a safety gate.

## 2. Locked architecture

1. Gate.io Public Spot `BTC_USDT` is the sole canonical global source for market data, live chart, candles and indicators, through the existing persisted feed and `global_market_data_reader_v1`.
2. The chart and analysis must consume the same validated batch and provenance.
3. The exchange adapter is separate and used only for execution, order status and fills after approval. Do not reconcile exchange candles/volumes/sequences into the analysis source.
4. Reuse `NativeOHLCVBatch`, existing Gate.io feed/reader, feature pipeline, Signal Agent, Strategy Policy V2, journal, Mother, witness, News Intelligence Brain, Learning Loop and existing dashboard. No duplicate engine, strategy, journal, frontend or monitor.
5. Missing, stale, gapped, malformed, mismatched, unprovenanced or unapproved evidence fails closed. Unknown is not zero and not PASS.
6. Keep execution disabled until the independent execution gates pass. Current state remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.

## 3. Evidence snapshot — 2026-11-02

### Candidate PR #410

PR #410 exact current head `9bb1dc7067744e52fa98b8158b932282b13c1b58` passed all five workflows after pinning the existing browser smoke job to Ubuntu 24.04. Full repository regression: **611 passed + 19 subtests**. Run links:

- Full repository regression: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716943
- Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716890
- Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716857
- Bounded Binance Spot WebSocket transport smoke (not Gate.io recovery): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716982
- Gate.io public candle contract smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399717171

Browser artifact digest: `sha256:8bad8bfecd9e40911cdfcd8e0c9e6a0a20d1f3016a29b552f603b3eae2d621de`. It proves 239 closed Gate.io candles, identical chart/signal batch hash, displayed close/volume and all candle values matching the API batch, responsive widths 390/768/1440 without overflow, and no browser-to-market-data request. Signal remains BLOCKED/NO_TRADE and execution OFF. The bounded WebSocket job is Binance Spot transport only; Gate.io WebSocket reconnect/recovery and 24-hour soak remain open. Gate.io Spot schema `gateio_spot_candlestick_v2` validates its 8-field response and closed-window flag; unsupported trade-count/taker-buy fields remain UNKNOWN.

### Candidate PR #408

Current head: `f25569a7d22e4e9382d05e9df61e5142b9381ce3`, OPEN/Draft/non-mergeable in its current stack. Local/VPS exact-head suite is reported as 742 passed + 66 subtests; focused risk/Strategy V2 suite 24 passed + 42 subtests. GitHub Actions returned no PR-triggered runs for this exact SHA. Earlier CI/browser evidence applies to an earlier SHA and must not be reused as current proof.

### Existing soak and OOS evidence

The previously recorded 24-hour persisted Gate.io REST-feed soak audit passed in the #398 lineage (1,440 samples / 86,400 seconds, no invalid rows or gaps above 90 seconds, no feed-service restarts). Reuse this evidence; do not repeat it merely for a new report. It does not establish Gate.io WebSocket recovery or trading performance.

Blind forward OOS verdict remains `G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS`. A successful workflow job is not an OOS/strategy pass.


### Uploaded sequence-semantics research note
The supplied `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md` is explicitly a 2026-10-10 draft and research-only artifact. Its own limitations say it did not inspect the repository or prove the current implementation. Preserve it as historical protocol research, not as a current Gate.io feed guarantee or release acceptance artifact. The active Gate.io OHLCV/chart path does not depend on individual-trade sequence semantics; do not reopen or port Tabdeal/Binance sequence assumptions into the Gate.io candle reader. Revisit the research only if a concrete execution/order-book feature needs a venue-specific event-identity or ordering contract, and then require current primary evidence plus adapter-scoped tests.

## 4. Mandatory release gates

| Gate | PASS requires | Current disposition |
|---|---|---|
| G0 — Scope and lineage | Canonical repo, exact SHA, reconciled PR ancestry, known VPS/runtime lineage | PARTIAL |
| G1 — Build and tests | Required tests/workflows on the exact proposed release SHA; negative tests and artifacts | PARTIAL (#410 exact head 9bb1dc7 passes 5/5 workflows; #408 must rebase onto current #406 and then pass exact-head CI/browser) |
| G2 — Data integrity | Gate.io source identity, closed/fresh bars, same-batch chart/analysis, gaps/duplicates/schema/numeric checks | PARTIAL (bounded REST/browser proof; WS recovery open) |
| G3 — Runtime resilience | Gate.io WS disconnect/reconnect, REST reconciliation/backfill, duplicate/gap handling, restart and authorized-runtime soak | BLOCKED |
| G4 — Frontend integration | Existing real entrypoint, browser evidence and deployed route/runtime parity on the reconciled release stack | PARTIAL |
| G5 — Decision safety | Independent structure/confirmation/strategy-quality approval, independent risk approval, fail-closed negative tests and adequate OOS observations | BLOCKED |
| G6 — Execution boundary | Authoritative execution venue contract, symbol/instrument mapping, precision/minimums, idempotency, order/fill/status/fee reconciliation and separate authorization | BLOCKED / OFF |
| G7 — Operations and security | Sole VPS lineage, least privilege, health/SSH/firewall, backup/restore and production rollback evidence | PARTIAL |
| G8 — Review and release | Independent review, non-overlapping stack, exact-final-SHA checks, release notes, runbook, rollback and explicit go/no-go | BLOCKED |

A gate is PASS only when linked evidence identifies exact SHA, workflow/run, artifact/hash, scope and limitations. “Implemented”, “reported”, “skipped”, “not run” and “local-only” are not PASS.

## 5. Delivery schedule

- **Nov 2–4:** exact-head #408 Actions/browser evidence; reconcile #410 with the main dependency stack; close chart acceptance only with source-to-render proof.
- **Nov 5–9:** Gate.io WebSocket recovery/fault-injection and authorized-runtime lineage/soak evidence using existing components.
- **Nov 10–12:** independent strategy/structure/confirmation and risk review; authoritative execution instrument mapping; scope freeze on Nov 12.
- **Nov 13–16:** reconcile the complete PR stack; exact-final-SHA CI/browser checks; release notes, limitations, configuration/secret guidance, operator runbook, health checks and rollback.
- **Nov 17–18:** final go/no-go. Any mandatory open gate blocks production-ready claims.
- **Nov 19:** deliver only the verified scope. Delivery does not authorize live trading.

## 6. Anti-duplication and long-life maintenance

- Search existing modules, schemas, routes, workflows, tests, PRs and docs before implementation.
- Extend canonical paths; never create a second chart/candle/indicator/strategy/journal/frontend/news pipeline.
- Version API/schema/policy changes and migration procedures; preserve old evidence and hashes.
- Every evidence record includes UTC time, exact SHA, endpoint/source/scope, artifact/hash, result and limitations.
- Keep unknown values explicit; fail closed on drift, stale data, missing provenance, clock anomalies and scope mismatch.
- Use deterministic replay and negative tests; live probes are bounded and read-only unless separately authorized.
- Document dependency versions, supported runtime, backup/restore, rollback, least-privilege service actions, and end-of-life policy.
- Keep secrets out of logs, prompts, artifacts and checkpoints. Preserve append-only audit trails.
- Keep one current checkpoint and immutable dated snapshots; no competing plan or duplicate status register.

## 7. Release decision

**HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.** The software delivery target remains 2026-11-19, but the mandatory runtime-resilience, independent decision/risk approval, OOS, execution-mapping and final-review gates are not all passed. Do not merge, deploy, enable execution or place orders based solely on candidate CI success.
