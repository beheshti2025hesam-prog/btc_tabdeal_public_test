# HES dashboard security, release, and rollback runbook

**Applies to:** the read-only persisted-feed dashboard candidate in PR #388.  
**Target date:** 2026-11-19.  
**Current disposition:** HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.  
**Production status:** this runbook is a prepared procedure, not evidence of a production deployment or rollback rehearsal.

## Security boundary

- Dashboard binds to `127.0.0.1:8765` by default. Do not expose it directly to the public internet; any remote access must be through an approved authenticated TLS reverse proxy and firewall policy.
- Public market data only. No account credentials, balances, order-submit route, or live execution permission are part of this dashboard.
- Keep `execution_enabled=false`, `orders_placed=false`, and `NO_TRADE_ONLY`; missing source, structure, strategy, mapping, or risk evidence must remain fail-closed.
- Use the locally pinned TradingView Lightweight Charts asset. Browser requests to exchange APIs or third-party chart CDNs are a test failure.
- Responses must include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy`, `Cache-Control: no-store`, and CSP directives `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.
- The page still uses inline script/style and therefore retains `'unsafe-inline'` for those directives. Treat this as a documented residual hardening item; do not describe the CSP as nonce/hash strict.

## Pre-release gate

1. Confirm the approved repository, branch, exact commit SHA, clean staged release artifact, and independent review.
2. Run the full repository suite and exact-head browser test. Browser evidence must show:
   - all displayed OHLC/time/volume values match the API payload;
   - chart and Signal Agent `input_batch_sha256` values match for the same 15m request;
   - no browser-to-exchange REST request or external chart CDN request;
   - visible candles, no console/page errors, and responsive viewport checks;
   - Signal Agent is `BLOCKED` / `NO_TRADE` while required providers are absent and execution is disabled.
3. Verify freshness, closed-candle integrity, source identity, symbol mapping evidence, risk/strategy approvals, access control, service user, firewall, health check, logs, and monitoring.
4. Verify a staged install and rollback in an isolated environment before production. Capture exact SHA-256 hashes and command output; do not infer success from CI alone.
5. Do not deploy until the frontend runtime and approved release target on the sole VPS are identified. Never clean, reset, or overwrite its dirty checkout as part of this procedure.

## Controlled release (not yet authorized)

- Build a release artifact from the reviewed exact SHA; record its hash and dependencies.
- Install to a new versioned release directory, not over the current release.
- Keep the dashboard loopback-only and paper/read-only. Do not enable any exchange order adapter or collector.
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
- Dashboard restart must not start a WebSocket collector or order path automatically.
- Simulate feed loss, dashboard process restart, and recovery in an isolated environment; verify the dashboard returns only after fresh persisted candles validate.
- Exercise rollback against a staged versioned install and prove the previous artifact hash is restored.
- Preserve the existing 24-hour feed soak evidence, but do not treat it as a dashboard deployment/rollback test.

## Evidence ledger

- Candidate PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/388
- Persisted-feed parent: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/383
- Signal Agent source candidate (not a separate merge target): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/387
- The recorded CI evidence applies only to the exact SHA shown in the corresponding workflow run. Production installation, production rollback, independent risk approval, and execution mapping remain separate gates.
