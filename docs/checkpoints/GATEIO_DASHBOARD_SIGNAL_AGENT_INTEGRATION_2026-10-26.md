# HES Trade Agent — Persisted Gate.io Feed + Signal Agent Integration Candidate
**Date:** 2026-10-26 (UTC)

## Disposition

**Local combined candidate tests: PASS — 599 passed, 5 subtests passed. Exact-head GitHub CI and browser-render evidence for this combined SHA are still pending. Product/release remains HOLD / NO_TRADE_ONLY.** Target delivery remains 2026-11-19. This candidate does not authorize merge, deployment, service activation, or live execution.

## Canonical data path

- Existing dashboard entrypoint: `web/dashboard.py`; no parallel UI was created.
- Public feed writer: `forward/global_market_data_gateio_v1.py`, running as three read-only systemd feeds for 15m/1h/4h.
- Canonical persisted reader: `forward/global_market_data_reader_v1.py`; both chart and Signal Agent route use it through the same `NativeOHLCVBatch`/cache path.
- Chart and signal routes: `GET /api/candles`, `GET /api/signal`, and `GET /healthz`.
- Both API responses expose the same source identity and `input_batch_sha256`; browser smoke now asserts the hash equality, `NO_TRADE`, blocked status, and `execution_enabled=false`.
- Browser must not make direct exchange REST requests; chart library remains locally vendored.
- Supported scope: Gate.io Spot / BTCUSDT / persisted closed candles at 15m, 1h, and 4h. Signal evaluation is scoped to 15m only.

## Implementation lineage

- Persisted-feed dashboard candidate base: PR #383 head `bf6627571802f2d1aaac930dc22fb6437b11ac04`.
- Signal Agent candidate source: PR #387 head `f82fa23017cd7e705fe5e208d7f8a5e6e6a102f6`.
- These were combined in an isolated workspace under `/srv/hes-evidence/gateio-persisted-feed-signal-agent-20261026`; the live VPS checkout `/opt/hes-trade-agent` was not modified by this integration work.
- The local combined tree preserves the persisted reader path from PR #383 while adding the Signal Agent route and contract tests from PR #387. It avoids merging the two candidate branches independently and does not create another dashboard.

## Verification so far

- Full local test suite on the isolated combined tree: **599 passed, 5 subtests passed**.
- Python source compile checks passed for the dashboard and Signal Agent modules.
- `node --check scripts/test_native_ohlcv_dashboard_browser_smoke.cjs` passed.
- The combined browser smoke now checks chart-vs-API candle parity, no direct exchange request from the browser, Signal Agent source/reader identity, equal input-batch SHA-256, `NO_TRADE`, blocked status, and execution disabled. Exact-head browser CI is pending until the candidate is pushed and a draft PR is created.
- Original PR #387 exact-head full-suite CI passed: 593 tests and 5 subtests; browser-render CI passed on its direct-source candidate. Original PR #383 browser-render CI passed on the persisted-feed chart candidate. These are separate candidate SHAs, not a substitute for testing the combined candidate.

## Sole VPS evidence (read-only inspection)

- Local runtime HEAD: `b2466bc118217dcc6446498effe38181589ed2db`; worktree is dirty. Do not reset, clean, checkout, or overwrite it.
- Exact active soak runner SHA-256: `435404c3694455015ef9d26c23544e44f5809dbf2dceefea3401704f8d0328a8`.
- Exact active reader SHA-256: `ef39445a1356de71a25d174ce30dd88dffb0d6377ac623c186203a3e5d120e41`.
- At 2026-10-26 11:31 UTC, the uninterrupted v2 soak had 1,421 valid samples and 85,346 seconds elapsed; all inspected samples were valid, max sample gap was about 60.742 seconds, and the independent auditor correctly returned `IN_PROGRESS` because no final summary existed yet. Do not restart the feed or soak before its final summary.
- The three read-only feed services and the soak service were active at the last check. A mocked disconnect/reconnect harness passed: first WebSocket attempt failed, second subscription succeeded, REST reconciliation was called on each loop, and reconnect was logged. Actual service-restart fault injection remains pending until the 24-hour run completes.
- Current analysis result remains `NO_TRADE`; `execution_enabled=false`, `orders_placed=false`.

## Still blocking release

- The actual dashboard is not installed or verified as a service on the sole VPS; the candidate frontend runtime/deployment path remains unverified. No deployment or service activation was performed.
- The final uninterrupted 24-hour soak summary, independent audit, final log SHA-256, and post-soak restart test are pending.
- Strategy-level structure/confirmation providers, risk approval, and executable venue symbol/instrument mapping remain unapproved. `NO_TRADE` is mandatory.
- Open PRs remain Draft/HOLD with no submitted reviews. Do not merge isolated PRs or infer readiness from CI alone.

## Release control

Keep the combined candidate Draft/HOLD until exact-head full-suite and browser CI pass, the soak and restart audit pass, the real frontend runtime path is proven, and independent review approves the final non-duplicated PR lineage. No live trading or deployment is authorized by this checkpoint.
