# HES dashboard security, release, and rollback runbook

**Applies to:** the read-only persisted-feed dashboard and the existing Gate.io public market-data collector release candidate (PR #410 code SHA `a0abac7...`, Mother integration PR #408 code SHA `cf2fad0...`).  
**Target date:** 2026-11-19.  
**Current disposition:** HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.  
**Production status:** the existing Gate.io market-data services are active on the sole VPS; the newer PR #410 collector candidate is not deployed. No dashboard release deployment or production rollback has occurred. An isolated temporary-directory versioned-release/rollback rehearsal passed; it does not replace production authorization or production rollback evidence.

## Security boundary

- Dashboard binds to `127.0.0.1:8765` by default. Do not expose it directly to the public internet; any remote access must be through an approved authenticated TLS reverse proxy and firewall policy.
- Public Gate.io market data only. No account credentials, balances, order-submit route, or live execution permission are part of this dashboard. The execution adapter remains a separate, disabled boundary.
- Keep `execution_enabled=false`, `orders_placed=false`, and `NO_TRADE_ONLY`; missing source, structure, strategy, mapping, or risk evidence must remain fail-closed. The backend collector is market-data-only and must never enable an order path.
- Use the locally pinned TradingView Lightweight Charts asset. Browser requests to exchange APIs or third-party chart CDNs are a test failure.
- Responses must include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy`, `Cache-Control: no-store`, and CSP directives `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.
- Dashboard client JavaScript and CSS are served as same-origin static assets; inline script/style and inline style attributes are removed. CSP `script-src` and `style-src` do not allow `unsafe-inline`. Regression tests assert this restriction.

## Pre-release gate

1. Confirm the approved repository, branch, exact commit SHA, clean staged release artifact, and independent review.
2. Run the full repository suite and exact-head browser test. Browser evidence must show:
   - all displayed OHLC/time/volume values match the API payload;
   - chart and Signal Agent `input_batch_sha256` values match for the same 15m request;
   - no browser-to-exchange REST request or external chart CDN request;
   - visible candles, no console/page errors, and responsive viewport checks;
   - Signal Agent is `BLOCKED` / `NO_TRADE` while required providers are absent and execution is disabled.
3. Verify freshness, closed-candle integrity, source identity, symbol mapping evidence, risk/strategy approvals, access control, service user, firewall, health check, logs, and monitoring.
4. Verify a staged install and rollback in an isolated environment before production. Capture exact SHA-256 hashes and command output; do not infer success from CI alone. The candidate now includes filesystem-only atomic version-switch/rollback tests, but those tests are not a production rollback rehearsal.
5. Do not deploy until the frontend runtime and approved release target on the sole VPS are identified. Never clean, reset, or overwrite its dirty checkout as part of this procedure.

## Controlled release (not yet authorized)

- Build a release artifact from the reviewed exact SHA; record its hash and dependencies.
- Install to a new versioned release directory, not over the current release.
- Keep the dashboard loopback-only and paper/read-only. Preserve the existing Gate.io collector services as a separate market-data dependency; do not start, stop, enable, restart or reconfigure them as part of a dashboard pointer switch. Do not enable any execution adapter or order path.
- Validate `/healthz`, `/api/candles`, `/api/signal`, CSP/security headers, same-batch hash, freshness, and `NO_TRADE_ONLY`.
- Switch the service target atomically only after an explicit release approval. Keep the previous release and configuration intact.

## Rollback procedure

Trigger rollback on failed health check, stale/invalid feed, mismatched source/batch hash, unexpected external network request, browser errors, security-header regression, service instability, or any execution-enabled/order-placed flag.

1. Stop the candidate dashboard service; do not stop the canonical Gate.io market-data feeds or paper evaluator.
2. Atomically point the dashboard service to the previously recorded release and configuration. Do not use `git reset`, `git clean`, or overwrite the existing dirty checkout.
3. Start only the previously approved read-only dashboard service.
4. Verify `/healthz`, source identity, closed-candle freshness, no order endpoints, `execution_enabled=false`, `orders_placed=false`, and browser/API batch consistency.
5. Record the failed SHA, previous SHA, timestamps, service state, log excerpt, evidence hashes, and reason. Keep release status HOLD until independently reviewed.

## Recovery/fault tests required

- Feed stale/missing/corrupt/duplicate/gapped/open/future candle data must fail closed.
- Dashboard restart must not start the backend Gate.io WebSocket/REST collector or any order path automatically. The collector is a separate systemd service.
- Simulate feed loss, dashboard process restart, and recovery in an isolated environment; verify the dashboard returns only after fresh persisted candles validate. The backend collector must separately pass WS disconnect/reconnect, bounded backoff, REST reconciliation/backfill, duplicate/conflict and unresolved-gap fail-closed tests.
- Exercise rollback against a staged versioned install and prove the previous artifact hash is restored.
- Preserve the existing 24-hour feed soak evidence, but do not treat it as a dashboard deployment/rollback test.

## Evidence ledger

- Candidate PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388
- Persisted-feed parent: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/383
- Signal Agent source candidate (not a separate merge target): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/387
- Exact-head validation on 2026-10-27: full repository suite 604 passed / 8 subtests; dashboard single-path tests passed; browser render and responsive checks passed at 390px, 768px, and 1440px with no horizontal overflow; public Binance Spot WebSocket-to-REST smoke passed (read-only transport test; not proof of Gate.io collector recovery).
- Isolated VPS runtime smoke on candidate SHA `a64afe129f41db66afb5b54724e1eb2cd2ab5665`: health 200 with fresh feed, 503 after the persisted 15m file was removed beyond cache expiry, 200 after restore, and 200 after process restart. Temporary checkout/process were removed; no VPS service was installed or changed.
- Isolated versioned-release rollback rehearsal on candidate SHA `b6f5fed89350dd3c9ba42e3722a7a8f2192bd78b`: valid release health 200; intentionally invalid release rejected; atomic pointer restored to the valid release; health returned to 200 and the restored dashboard SHA-256 matched the saved pre-release digest. Temporary release directories and process were removed.
- The new systemd unit template passed `systemd-analyze verify` in an isolated normalized staging root on 2026-10-27. This did not install the unit, reload systemd, enable/start a service, or change production files.
- The recorded CI evidence applies only to the exact SHA shown in the corresponding workflow run. Production installation, production rollback, independent risk approval, and execution instrument mapping remain separate gates.


## 2026-11-02 — Gate.io collector and Mother release-candidate update

### Exact candidate evidence

- PR #410 code-bearing SHA `a0abac7d23893cf8d628041d8033ec9b5bee119e`: **5/5 exact-head workflows passed**; full repository suite **628 passed + 19 subtests**. The Native WebSocket Live Smoke is Binance Spot only; the Gate.io public candle contract smoke is the Gate.io-specific transport/schema evidence.
- PR #408 code-bearing SHA `cf2fad0c7363a33181bc94c3b2e4f6155d8b0a72`: **4/4 exact-head workflows passed**; full repository suite **791 passed + 64 subtests**. It is based on current PR #406 and GitHub reports mergeable.
- Gate.io collector/native-adapter/reader targeted suite: **33 passed**. Systemd unit syntax for the 15m/1h/4h collectors and optional soak service passed `systemd-analyze verify`; the only warning was for an unrelated existing Xray unit.

### Existing collector now versioned — not deployed

- The previously running collector was present on the VPS working branch but absent from the release PR chain. The existing implementation is now included in PR #410 with its wrapper, 24h read-only soak script, operator README, 15m/1h/4h systemd units, security/sandbox drop-ins, and optional soak unit. No second collector was created.
- REST bootstrap/reconciliation reuses `GateioSpotKlineSource` and its eight-field closed-candle contract. WebSocket is a wake-up channel only; persisted candle values always come from REST. Both base-volume `a` and quote-volume `v` are required for a wake-up; neither is substituted.
- The collector keeps at most 500 contiguous closed candles, merges by open time, atomically repairs missing recent bars when available, and fails closed on malformed rows, conflicting duplicates or unresolved gaps. It reconciles REST at least every 20 seconds while subscribed and uses bounded reconnect backoff.
- The candidate fixes the previous silent quote-volume-to-base-volume fallback. These changes are in PR #410 only; they have **not** been deployed to the running VPS services.

### Runtime and safety disposition

- At the read-only audit, the three Gate.io collector services, readonly dashboard, paper evaluator and learning loop were ACTIVE with `NRestarts=0`. The 24-hour Gate.io REST-feed soak passed (1,440 samples / 86,400 seconds, zero invalid rows, no gap above 90 seconds, no feed-service restarts).
- The browser-facing dashboard stream is disabled. The backend collector uses Gate.io WS wake-ups with REST-only persisted values. Live Gate.io WS subscription/reconnect behavior has not yet been independently verified under fault injection.
- Dashboard runtime points to `/opt/hes-trade-agent/current` → `releases/2e8d3859...`; paper evaluator and learning loop run from the dirty root branch `feat/gateio-global-market-data-v1`, SHA `060d0d36...`. This runtime-lineage split remains a release blocker.
- The blind OOS evaluator remains `G6_BLOCKED_INSUFFICIENT_FORWARD_OBSERVATIONS` (95 vs 4,000); its frozen `data/trades.csv` source is legacy Tabdeal trade-event data, not Gate.io. Do not use it to approve the current Gate.io strategy.
- The 24h journal contains 96 NO_TRADE decisions; 95 have complete 24h forward windows and one is not yet mature. No gate-qualified avoided-loss or missed-profit attribution has been established. Learning remains `READ_ONLY_HYPOTHESIS_ONLY`; no policy mutation, execution or orders.
- No PR merged; no service restarted or reloaded; no production pointer changed; no account connected; no order executed. Current disposition remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.
