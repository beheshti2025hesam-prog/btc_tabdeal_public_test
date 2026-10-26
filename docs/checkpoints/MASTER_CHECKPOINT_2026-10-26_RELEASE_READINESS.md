# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-26 (UTC)  
**Rule:** Memory = project map/context; GitHub = technical truth; Chat = conversation log.

## Current decision
- **Delivery target:** 2026-11-19.
- **Risk checkpoint:** 2026-10-26.
- **Release:** **HOLD / NO_TRADE_ONLY**. No live trading, merge, or deployment is authorized by this checkpoint.
- **Infrastructure:** exactly **one VPS**; live state was verified rather than inferred.
- **Canonical repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`.
- **Release criteria and schedule:** [Release Readiness & Delivery Control](../RELEASE_READINESS.md).

## Locked decisions — do not rediscover without new evidence
1. One unified, validated global market-data source feeds charts/candles and analysis through the same batch/provenance.
2. Exchange adapter is for order execution and order status only. Do not revisit chart candle sequence or exchange-volume reconciliation unless new evidence shows an execution-relevant issue.
3. Reuse the existing dashboard candidate `web/dashboard.py`; do not build a parallel frontend.
4. Gate.io is the interim operational global-feed candidate. Binance access was previously reported unavailable; do not reopen absent new evidence.
5. Missing, stale, gapped, malformed, mismatched, or unapproved evidence fails closed. Risk context and execution symbol mapping are separate approvals.
6. One VPS only; no invented second machine.

## Verified evidence — 2026-10-26

### Sole VPS and runtime
- Runtime checkout: `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, exact HEAD `b2466bc118217dcc6446498effe38181589ed2db`.
- Worktree remains dirty: **11 tracked changes and 50 untracked paths** (61 status entries). Do not reset, clean, checkout, or overwrite it.
- Local full suite on the dirty runtime checkout: **417 passed**.
- Active market-data services after the restart test: `hes-global-market-data-gateio.service`, `hes-global-market-data-gateio-1h.service`, and `hes-global-market-data-gateio-4h.service`. The completed soak service is inactive as expected.
- The actual dashboard is **not installed or verified as a service on the VPS**; no dashboard deployment or service activation occurred.

### Combined dashboard + Signal Agent candidate
- Draft PR [#388](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388) is stacked on persisted-feed dashboard PR #383 and reuses the existing dashboard entrypoint.
- Application-code head `955a747f21a335b83f2c78799c81f9117adfac68`: full repository regression **599 passed, 5 subtests passed** ([run 40317136628](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136628)); dashboard single-path **PASS** ([run 40317136487](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136487)); browser render/pixel **PASS** ([run 40317136520](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40317136520)).
- Browser artifact SHA-256: `15c62ebe7a486ca6fd5c5c5e70c04ddd500c033802239ee7f59973d4628e826b`.
- Browser proved chart and Signal Agent used the same batch hash `40fa0e34fe6cdde3c0bce92c48c9768428a3288bf6611aa1fbc16c9d72e08332); 239 closed candles rendered; visible pixels 1,709 green / 1,239 red; no direct exchange REST request from the browser and no external chart CDN; displayed close and volume matched the source.
- Signal result remains `BLOCKED / NO_TRADE`; execution is disabled. Native OHLCV WebSocket live smoke was **SKIPPED**, not passed.
- PR #387 is the alternate direct-source Signal Agent candidate; PR #383 is the persisted-feed chart candidate. PR #388 combines the relevant Signal Agent changes on top of #383. Do not merge #383 and #387 independently or merge PR #388 before review of ancestry and overlap. PR #362 is also an overlapping Signal Agent candidate. PR #345 and #349 are closed/unmerged.

### 24-hour soak and restart audit
- The uninterrupted v2 Gate.io read-only soak **PASSED**: duration **86,400 seconds**, **1,439 samples**, max gap **60.742 seconds**, wall duration **86,400.094 seconds**, no errors.
- Soak log SHA-256: `df499e17f6366e69ab14ab17adc2ed7e2ac9e205e4d1b1925bbd6284de975c44`.
- Independent audit report: `/srv/hes-evidence/gateio/gateio_feed_soak_audit_20261026.json`; report SHA-256 `ecc9dff5780edfb8d25e32bab698a27f362dc16b7dedbc549430f4990bfdc8bd`. Auditor SHA-256: `dff1f76e86ebdb5dbc9eda6f648bfc7a6f8b4094ee470f761e236cea8e9f9446`.
- Controlled post-soak restart test **PASSED**: 15m service PID changed from `237849` to `273642`; service returned active; `HES_GLOBAL_MARKET_START` and `HES_GLOBAL_MARKET_WS_SUBSCRIBED` were observed; the canonical reader accepted all 15m/1h/4h feeds after restart with unique, strictly increasing timestamps.
- Restart evidence: `/srv/hes-evidence/gateio/gateio_feed_restart_fault_test_20261026.json`; SHA-256 `426620bc806b2ead26843e0e361ca1b658468b3e2d69d3cf67cd16da65968d0f`.
- A separate **mocked** disconnect/reconnect harness passed (two connection attempts, REST reconciliation twice, subscription and reconnect logged). This is not a live network fault-injection result.
- After restart, a one-shot read-only analysis consumed the latest closed 15m candle at **2026-10-26 11:45 UTC** and returned `NO_TRADE`; `execution_enabled=false`, `orders_placed=false`.

## Remaining release blockers, in priority order
1. Verify the actual frontend runtime/deployment and rollback path on the sole VPS. Candidate browser CI is not proof of production installation; no deployment or service activation is authorized here.
2. Wire and independently validate structure/confirmation and strategy-quality evidence for the Gate.io scope.
3. Obtain independent risk approval and executable venue symbol/instrument mapping evidence. Until then, `NO_TRADE` and execution OFF remain mandatory.
4. Complete operational/security review, independent PR review, exact final-SHA checks, and final go/no-go. Draft PRs have no submitted reviews.

## Schedule control
- **2026-10-26:** risk checkpoint; completed today: exact VPS verification, combined candidate CI/browser proof, uninterrupted soak audit, controlled restart/recovery, and current one-shot NO_TRADE analysis. Remaining blockers stay explicit; no gate waivers.
- **2026-10-27–11-02:** verify production frontend/runtime and rollback path; reconcile exact PR ancestry.
- **2026-11-03–11-09:** resilience and risk/mapping evidence.
- **2026-11-10–11-15:** final candidate, non-overlapping PR stack, release docs and independent review.
- **2026-11-16–11-18:** scope freeze and exact-final-SHA go/no-go.
- **2026-11-19:** deliver only verified scope; software delivery does not authorize trading.

## Anti-duplication protocol
Before implementation: search repository, open PRs, tests, workflows and checkpoints. Prefer reuse or targeted optimization of existing code. Never turn a skipped workflow, candidate PR, or local-only state into a verified pass. Do not tune strategy thresholds to satisfy a release gate.

## Provenance
This is a documentation-only candidate on branch `docs/release-readiness-checkpoint-2026-10-26`. It does not modify application code, runtime, VPS services, or trading behavior. Review and required CI remain necessary before merge.
