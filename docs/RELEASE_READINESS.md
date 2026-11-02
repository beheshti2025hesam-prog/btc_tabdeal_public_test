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

PR #410 code-bearing SHA `9bb1dc7067744e52fa98b8158b932282b13c1b58` passed all five exact-head workflows after the existing browser workflow was pinned to Ubuntu 24.04. Later PR #410 commits only updated documentation; do not transfer the CI claim to those documentation-only SHAs.

- Full repository regression, **611 passed + 19 subtests**: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716943
- Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716890
- Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716857
- Bounded Binance Spot WebSocket transport smoke (not Gate.io recovery): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399716982
- Gate.io public candle contract smoke: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41399717171

Browser artifact SHA-256: `8bad8bfecd9e40911cdfcd8e0c9e6a0a20d1f3016a29b552f603b3eae2d621de`. It proves 239 closed Gate.io candles, same-batch chart/signal/API parity, close/volume match, responsive 390/768/1440 widths without overflow, and no browser market-data request or external chart CDN. Signal remains BLOCKED/NO_TRADE and execution OFF.

### Candidate PR #408

PR #408 is OPEN/Draft and GitHub reports mergeable. Exact head `cf2fad0c7363a33181bc94c3b2e4f6155d8b0a72`, based on current PR #406 head `9d761f0c7b140de52a3a7a1afc3f8e0ad7154927`; zero commits behind. The pre-rebase branch is preserved at `archive/pr-408-pre-rebase-2026-11-02`.

All four exact-head workflows passed:

- Full repository regression, **791 passed + 64 subtests**: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900557
- Native OHLCV dashboard single path: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900566
- Blind forward OOS evaluator workflow: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900552
- Browser render/responsive proof: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/41401900603

Browser artifact ID `13122300672`, SHA-256 `ed89e67dcfec6ad79247aaace3dfab57023045222ae772da68796bea380eb2aa`: PASS; Gate.io Public Spot BTC_USDT through `global_market_data_reader_v1`; 239 closed candles; latest closed bar age 55.5s; chart/API/all-candle batch parity; close and volume match; responsive 390/768/1440 without overflow; no browser market-data request or external chart CDN. The strategy endpoint remains BLOCKED/NO_TRADE and execution instrument mapping remains unverified.

Rebase fixes: explicit Opportunity Policy scopes (default Gate.io BTC_USDT/15m); journal legacy-row compatibility test; runtime-path newline fixture; final-checkpoint test isolation from Git reset; repository-relative report script paths; and Ubuntu 24.04 browser runner pin. The full suite also passed on the clean VPS-side rebase clone. Original dirty VPS checkout was not modified.

### Gate.io data and runtime evidence

- Canonical source remains Gate.io Public Spot BTC_USDT. Chart and analysis consume the same persisted closed-candle batch via `global_market_data_reader_v1`; execution remains a separate adapter.
- The three existing Gate.io candle collector services (15m, 1h, 4h), readonly dashboard, paper evaluator and learning loop were ACTIVE with `NRestarts=0` at the read-only audit. Latest persisted bars were 06:15Z (15m), 06:00Z (1h), 04:00Z (4h).
- The previously recorded 24-hour Gate.io REST-feed soak passed: 1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no feed-service restarts. Reuse this evidence; do not repeat it just to duplicate a report.
- Gate.io WebSocket is disabled. The accepted chart/analysis path is REST closed candles; WebSocket reconnect is not a release requirement unless a concrete strategy need is established. The Binance Spot WebSocket smoke on #410 is not Gate.io evidence.
- Runtime lineage remains PARTIAL: dashboard runs from `/opt/hes-trade-agent/current` → `releases/2e8d3859...`; paper evaluator and learning loop run from `/opt/hes-trade-agent` root, branch `feat/gateio-global-market-data-v1`, SHA `060d0d36...`, dirty worktree. This split was read-only inspected and left unchanged.

### Paper journal and Learning Loop

- 24-hour decision report generated 06:27Z: 96 NO_TRADE decisions.
- 95 decisions have complete, gap-free 24-hour forward windows; one recent decision is not yet mature. No gate-qualified directional counterfactual established an avoided loss or missed profit. A rejected proposal's later stop-loss touch is diagnostic only, not a counted avoided loss.
- Learning Loop remains `READ_ONLY_HYPOTHESIS_ONLY`; target policy is unset; `policy_mutation_enabled=false`, `execution_enabled=false`, `orders_placed=false`. No threshold or strategy policy was tuned from these observations.

### OOS source qualification

The blind evaluator workflow completed, but its scientific verdict remains `G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS`: 95 forward observations vs 4,000 required. Its frozen `data/trades.csv` source is legacy Tabdeal trade-event data, not the canonical Gate.io candle source. Preserve it as historical research only; it cannot approve the current Gate.io strategy or establish profitability.

The supplied sequence-semantics document remains research-only. It does not justify applying trade-sequence semantics to the Gate.io OHLCV candle path. Keep sequence contracts adapter-specific and UNKNOWN unless a concrete execution/order-book feature needs them.

## 4. Mandatory release gates

| Gate | PASS requires | Current disposition |
|---|---|---|
| G0 — Scope and lineage | Canonical repo, exact SHA, reconciled PR ancestry, known VPS/runtime lineage | PARTIAL (PR #408 now aligns to #406; dashboard vs paper/learning code roots still differ) |
| G1 — Build and tests | Required tests/workflows on exact proposed release SHA; negative tests and artifacts | PARTIAL (#410 5/5 and #408 4/4 candidate workflows pass; final combined-stack SHA still required) |
| G2 — Data integrity | Gate.io source identity, closed/fresh bars, same-batch chart/analysis, gaps/duplicates/schema/numeric checks | PASS for bounded Gate.io Spot scope (8-field REST schema, 239-bar parity, latest age 55.5s, prior 24h REST soak) |
| G3 — Runtime resilience | Existing REST collector continuity, stale/gap detection, restart/backfill recovery and duplicate handling | PARTIAL (services active, zero restarts; deterministic restart/backfill fault-injection proof remains) |
| G4 — Frontend integration | Existing real entrypoint, browser evidence and deployed route/runtime parity on reconciled release stack | PARTIAL (candidate browser proof passes; deployed runtime parity remains open) |
| G5 — Decision safety | Independent structure/confirmation/strategy-quality approval, independent risk approval, fail-closed negative tests and adequate Gate.io-based forward outcomes | BLOCKED |
| G6 — Execution boundary | Authoritative execution venue contract, symbol/instrument mapping, precision/minimums, idempotency, order/fill/status/fee reconciliation and separate authorization | BLOCKED / OFF |
| G7 — Operations and security | Sole VPS lineage, least privilege, health/SSH/firewall, backup/restore and production rollback evidence | PARTIAL (services healthy; runtime roots and rollback proof remain) |
| G8 — Review and release | Independent review, non-overlapping stack, exact-final-SHA checks, release notes, runbook, rollback and explicit go/no-go | BLOCKED |

A gate is PASS only when linked evidence identifies exact SHA, workflow/run, artifact/hash, scope and limitations. A successful evaluator workflow is not a successful strategy verdict. “Implemented”, “reported”, “skipped”, “not run” and “local-only” are not PASS.

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
