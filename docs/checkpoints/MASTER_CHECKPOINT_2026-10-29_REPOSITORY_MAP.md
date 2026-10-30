# HES Trade Agent — Master Checkpoint: Repository Map
**Date:** 2026-10-29  
**Target application delivery date:** 2026-11-19  
**Status:** Repository identified as the canonical *currently evidenced project/data-foundation repository*; production-app repository identity and release readiness are NOT yet proven.

## Canonical repository currently evidenced
- Repository: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- Default branch used for this checkpoint branch base: `main`
- Verified README path: `README.md`
- README blob SHA observed: `b42ca7a1666cba9151c65ad37e6304945e87e16c`
- README describes this as the first Tabdeal BTC/USDT futures market-data collector for HES Trade Agent. It explicitly says this component does not use Binance, does not require a Tabdeal API key, does not access balances, does not place orders, and does not trade.
- Therefore, treat this repository as the verified HES project/data-collection repository, NOT automatically as the complete production application repository.

## Existing paths / references to reuse (do not rebuild without evidence)
- `README.md` — project identity and the current collector's scope.
- `web/dashboard.py` — referenced in project PR discussions as an existing dashboard path; verify on the selected branch before editing.
- `NativeOHLCVBatch` — referenced as the canonical OHLCV data contract in prior project work; locate and inspect its actual implementation/tests before changing anything.
- PR #297 — data-contract / canonical OHLCV infrastructure reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/297
- PR #346 — candidate dashboard/front-end work, NOT an approved release: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/346
- PR #354 — related UI work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/354
- PR #365 — Gate.io data-path work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/365
- PR #375 — existing dashboard/chart-data integration reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/375
- PR #386 — release-readiness / documentation work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/386
- The above PRs are references for investigation, not proof that they are merged, passing, or production-approved. Verify live state and exact commit SHA before relying on them.

## Documentation paths and current branch state
- `docs/RELEASE_READINESS.md` — created on this documentation branch as an evidence-based release contract; it is not yet on the default branch.
- `docs/checkpoints/MASTER_CHECKPOINT_2026-10-26_RELEASE_READINESS.md` — the exact path could not be fetched from the default branch and remains unverified at that location.
- This checkpoint and release-readiness contract are on `docs/master-checkpoint-repository-map-2026-10-29`; they are reviewable documentation changes, not merged/default-branch state.

## Anti-reinvention rules
1. Inspect the current repository, branches, existing modules, tests, and PR diffs before implementing anything.
2. Reuse the existing frontend/dashboard and canonical market-data contract where verified. Do not create a parallel app, parallel OHLCV contract, or duplicate market-data pipeline.
3. Keep market-data/analysis sourcing separate from exchange execution adapters. Do not add sequence reconciliation unless a documented execution-critical requirement proves it necessary.
4. Never promote PR #346 or any candidate PR to approved/production status without exact-SHA checks, required CI/tests, artifact/provenance checks, and explicit release gates.
5. No live trading or deployment permission is implied by this checkpoint. Maintain HOLD / NO_TRADE_ONLY until the release and safety gates pass.

## Work completed on this documentation branch (2026-10-29)
- Added `docs/RELEASE_READINESS.md` with evidence-backed blockers, release gates, the one-VPS constraint, anti-reinvention rules, and the 2026-11-19 target.
- Added a repository map checkpoint and verified that the saved file can be read back from this branch.
- No application code, VPS files, services, credentials, deployment, or trading behavior was changed.

## Next required discovery gates
- Identify the real application repository/production entry point, using repository metadata, imports, deployment manifests, and live runtime evidence rather than names alone.
- Verify whether `web/dashboard.py` and `NativeOHLCVBatch` exist in the chosen branch; identify their tests and callers.
- Inspect PRs #297, #346, #354, #365, #375, #386: state, head/base SHAs, changed files, CI, merge status, and overlap; do not merge as a shortcut.
- Verify the one authorized VPS and runtime target; do not assume a second VPS.
- Complete remaining operator documentation (reproducible build/test steps, configuration/secrets guidance, rollback/recovery, health checks, security checklist) after the real application repository/path is accessible and existing docs are inventoried; extend existing docs rather than duplicating them.
- Target delivery date remains 2026-11-19. This is a planning target, not a claim of readiness.

## Truthful status
The README was fetched from the default branch. The checkpoint is intentionally being added on a separate documentation branch for review; it does not alter the default branch or approve a release.


## Gate.io continuation update — 2026-10-29
- Do not lose the active market-data decision: Gate.io public Spot `BTC_USDT`, candle profiles `15m`, `1h`, `4h`, with PR #365 as the selected source path. Do not restore Binance PR #345 as default without a fresh evidence-backed decision.
- PR #375 is the existing stacked, read-only Gate.io dashboard integration candidate. Its description reports REST/API parity and browser-render CI on a GitHub Actions runner, but no production VPS chart parity. Gate.io WebSocket smoke is SKIPPED, not passed; 24-hour soak, reconnect/restart/session isolation remain required.
- Issue #393 / PR #394 is the existing strategy-evidence fix candidate. Reuse the existing StrategyEvidenceProvider and feature/confirmation/risk modules; do not create a parallel strategy engine. Gate.io base/quote volume may be used according to documented semantics; trade count and taker-buy flow remain UNKNOWN/unavailable and must never be fabricated or treated as passing.
- PR #394 remains candidate-only until exact-head CI, independent structure/confirmation and risk approvals, execution instrument mapping, and native Gate.io dashboard stream evidence are independently checked.
- Current release posture remains `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`. No merge, deployment, live order, or threshold tuning is authorized by this checkpoint.


## Master checkpoint refresh — 2026-10-30 (verified live state)

**Disposition: PARTIAL / HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. Delivery target remains 2026-11-19.** This update records read-only checks and a refresh of existing reports; it does not authorize merge, deployment, service restart, policy mutation, or trading.

### Canonical architecture lock
- Gate.io public Spot `BTC_USDT` is the sole canonical source for market data, closed candles, chart, and analysis/indicator input. Existing persisted feed + `global_market_data_reader_v1` remain the path.
- Execution venue adapters are separate and limited to order submission/status once separately approved. Do not use execution-venue candles for analysis, mix source batches, or reconstruct candle data from trade sequence IDs.
- Reuse the existing dashboard, reader, feature pipeline, validators, journal, and learning loop. No parallel frontend or duplicate engine.

### Live verification — 2026-10-30 06:05 UTC
- Sole reachable VPS: SentinelX ping/state OK. Checkout `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `060d0d36ae6140a03d9a74495bb3899637ed3827`.
- Working tree has 130 short-status entries, including tracked deletions and untracked files. Preserve the dirty tree; do not reset, clean, checkout, overwrite, or bulk-stage/commit. This is not a clean approved release SHA.
- Gate.io 15m/1h/4h feeds, read-only dashboard, strategy learning loop, and paper evaluator are active. Dashboard health HTTP 200; 240 candles; chart and signal use identical batch SHA-256 `6b3de9c20ade59c06e53a73a1713485ca21e11573d6216dc3688deb3cdcc7353`; latest closed candle age about 330 seconds at check.
- Existing frontend/data contract gate: 15/15 PASS. Static assets and candle/signal APIs respond; POST `/api/signal` returns 405. Signal remains `NO_TRADE`; `execution_enabled=false`; `execution_instrument_mapping_verified=false`. This is HTTP/API verification, not fresh browser pixel parity or release approval.
- Existing 24-hour decision report refreshed at `2026-10-30T06:05:29Z`: 96 `NO_TRADE` decisions. No orders and no policy mutation.
- Matured 24–48h cohort: 96 decisions; 95 complete gap-free 24h horizons, one remains incomplete until exact boundary coverage; zero tracker boundary mismatches. At 24h, 2 avoided-loss hypotheses and 2 missed-profit hypotheses among 4 decisions with valid directional geometry; 91/95 decisions are unclassifiable because no valid frozen directional setup/risk geometry exists; 79 are large-move context only. These are gross counterfactual hypotheses, not causal proof or net profitability; cost model is unconfigured.
- Learning report: zero gate-approved candidates and zero resolved eligible outcomes; win rate remains null/not calculable. Do not claim all no-trade decisions were correct or assign profit/loss savings.
- Core services remained active after the check; no restart was needed.

### Release blockers
1. Strategy structure/confirmation and strategy-quality providers remain unapproved/unwired; fail-closed `NO_TRADE` is correct for the current unknown/unconfirmed state.
2. Independent risk approval and executable venue instrument mapping remain unverified.
3. Fresh browser render/pixel parity and full regression on one exact clean release SHA are still required.
4. Reconcile dirty checkout and active runtime to one reviewed immutable release SHA without disturbing user files.
5. Encrypted off-host backup/external alerting and remaining operational recovery/security gates remain open.
6. The 24h Gate.io soak service is currently inactive; validate historical soak final-summary/hash lineage against the candidate/runtime before claiming the gate covers today's release.

### Delivery controls
- 2026-11-12: scope freeze and go/no-go.
- 2026-11-16: release candidate only after exact-SHA tests, source/chart parity, soak/restart resilience, backup/rollback, security audit, and independent review pass.
- 2026-11-19: target delivery, not permission to waive mandatory gates.

### Next actions
1. Preserve and inventory dirty/untracked file hashes; reconcile runtime and source lineage.
2. Verify existing soak evidence and artifact hashes; if insufficient, use the existing Gate.io soak mechanism for one uninterrupted run and independent audit.
3. Review overlapping PR ancestry/exact heads (#383/#387/#388 and #397) before any merge.
4. Wire and test source-compatible Gate.io structure/strategy-quality evidence using existing modules.
5. Complete independent risk approval and executable instrument mapping.
6. Run full regression and real-browser render/pixel verification on one exact release SHA; document recovery and rollback.

Safety invariants: `execution_enabled=false`, `orders_placed=false`, `policy_mutation_enabled=false`. GitHub is technical truth; this checkpoint is a review-branch document and is not yet default-branch state.


## Continuation update — 2026-10-30

- Focused local regressions: 66 passed across 10 existing Gate.io, NO_TRADE, learning, strategy-gate, and risk test modules. These ran against the dirty checkout, not the immutable release artifact; the release artifact lacks the tests tree, so this is not exact-release proof.
- Existing Gate.io 24h soak log SHA-256: cc457ea7172d9d011b0e6faf39eea34d55ab43bfbe56966e38e1bba88924e7b7. Its final record says 1,439 samples, 86,400 seconds, passed=true, finished 2026-10-29 06:33:53 UTC. Historical log preserved; the soak service is inactive after the completed run. This proves that run's sampling result, not independent audit or current exact-release lineage.
- PR #394 exact head 770ff7b0eeab6b79537e60ddd9f2e06751c1b559 has successful GitHub Actions: full repository regression run 40902025442; browser render/pixel run 40902025517; Gate.io Spot WebSocket-to-REST smoke run 40902025502. The WebSocket smoke reconciled one closed Spot kline to REST; this is bounded smoke, not a 24h stream soak. PR #394 has no submitted reviews and remains Draft/Open.
- PR #388 head 2e8d3859ef154b030e0965ad4479f3fad36ae4c0 also has successful full-suite, browser, and single-path CI from runs 40474732832, 40474732841, and 40474732907. PRs #383/#387/#388/#394 overlap or stack; do not merge siblings independently.
- Release remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. Open blockers: independent strategy/confirmation and risk approval; executable instrument mapping; reconcile dirty checkout with exact runtime SHA; off-host encrypted backup and external alerting; independent review; soak evidence lineage. No orders, deployment, or policy changes were made.
