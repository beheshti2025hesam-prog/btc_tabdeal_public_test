# HES dashboard security, release, and rollback runbook

**Applies to:** the Gate.io persisted-feed + Signal Agent + canonical journal dashboard candidate in PR #398.  
**Target date:** 2026-11-19.  
**Current disposition:** HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.  
**Production status:** no production deployment or production rollback has occurred. Isolated tests do not replace production authorization or a production rollback rehearsal.

## Security boundary

- Dashboard binds to `127.0.0.1:8765`. Do not expose it directly to the public internet; remote access must use an approved authenticated TLS reverse proxy and firewall policy.
- Gate.io public Spot BTC_USDT is the sole canonical chart/analysis source. The browser consumes the persisted reader; it must not call exchange REST endpoints or external chart CDNs.
- Exchange/broker adapters are separate execution concerns. No account credentials, balances, order-submit route, or live execution permission are part of this dashboard.
- Keep `execution_enabled=false`, `orders_placed=false`, and `NO_TRADE_ONLY`; missing source, structure, strategy, mapping, confirmation, or risk evidence must remain fail-closed.
- Use the locally pinned TradingView Lightweight Charts asset.
- Responses must include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy`, `Cache-Control: no-store`, and CSP directives `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.
- Dashboard client JavaScript and CSS are same-origin static assets; inline script/style and inline style attributes are removed. CSP does not allow `unsafe-inline`.

## Canonical journal write boundary

Signal decisions must append to the already-existing canonical file consumed by the paper evaluator and Learning Loop:

`/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl`

The dashboard systemd unit must set `HES_TRADE_JOURNAL_PATH` to that exact absolute path. Do not use a release-relative `PROJECT_ROOT/data/forward` fallback: the dashboard is launched through `/opt/hes-trade-agent/current`, which resolves into an immutable versioned release.

The dashboard service remains read-only for releases and market data. Its only write exceptions are the canonical journal file and its pre-created lock file:

- `/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl`
- `/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl.lock`

Before starting the candidate service, verify the canonical journal already exists and is owned by `sentinelx:sentinelx`. If the lock file does not exist, create it during the privileged installation preflight as `sentinelx:sentinelx`, mode `0600`; do not replace its inode while the dashboard is running. The unit must retain `ReadOnlyPaths=/opt/hes-trade-agent/releases /opt/hes-trade-agent/data/forward` and grant only the two file-level `ReadWritePaths` exceptions above. Never grant write access to the whole `data/forward` directory. The journal writer uses an exclusive file lock, append-only records, fsync, and stable evidence-derived event IDs. Repeated polling for identical closed-candle evidence must resolve as `ALREADY_RECORDED`, not append duplicates.

The `GET /api/journal` projection is read-only. It must validate JSONL integrity, duplicate event IDs, timestamps, and outcome separation; it must never infer realized outcomes. Signal decisions must keep `outcome=null` and `closed_at=null`. Paper outcomes remain separate append-only records.

## Pre-release gate

1. Confirm the approved repository, branch, exact commit SHA, clean staged release artifact, and the recorded second-pass technical audit by the project pair (owner + assistant). This is an internal audit, not an independent human approval. The GitHub ruleset must match the declared two-person team; if it still requires an unavailable third-party approval, keep HOLD rather than bypassing it.
2. Run the full repository suite and exact-head browser test. Browser evidence must show:
   - displayed OHLC/time/volume values match the API payload;
   - chart and Signal Agent `input_batch_sha256` values match for the same 15m request;
   - no browser-to-exchange REST request or external chart CDN request;
   - visible candles, no console/page errors, and responsive viewport checks;
   - Signal Agent remains `BLOCKED` / `NO_TRADE` while required providers are absent and execution is disabled;
   - one immutable Signal decision is recorded for a new evidence identity, repeat polling returns `ALREADY_RECORDED`, and the existing Learning Loop sees the same canonical journal hash.
3. Verify the canonical journal and lock file paths, owner/mode, exact `HES_TRADE_JOURNAL_PATH`, file-level write exceptions, and that the dashboard service cannot write other market-data or report files.
4. Verify freshness, closed-candle integrity, Gate.io source identity, symbol mapping evidence, independent structure/confirmation/risk evidence, execution instrument mapping, access control, service user, firewall, health checks, logs, and monitoring.
5. Verify a staged install and rollback in an isolated environment. Capture exact SHA-256 hashes and command output; do not infer success from CI alone.
6. Do not clean, reset, or overwrite the sole VPS dirty checkout. Do not deploy until the real frontend runtime, approved release target, permissions, exact-head CI checks, and owner-verified two-person ruleset are established. Do not fabricate an independent review or bypass a GitHub rule.

## Controlled release (not yet authorized)

- Build a release artifact from the exact SHA that passed the required CI checks and the recorded internal technical audit; record its hash and dependencies.
- Install to a new versioned release directory, not over the current release.
- Preserve the canonical journal file and its lock inode. Pre-create the lock file if absent before applying the service sandbox.
- Keep the dashboard loopback-only and paper/read-only. Do not enable any exchange order adapter or collector.
- Install the reviewed service unit with the explicit canonical journal path and only file-level write exceptions.
- Validate `/healthz`, `/api/candles`, `/api/signal`, `/api/journal`, CSP/security headers, same-batch hash, freshness, journal write/readback, deduplication, and `NO_TRADE_ONLY`.
- Switch the service target atomically only after explicit release approval. Keep the previous release, service unit, and configuration intact.

## Rollback procedure

Trigger rollback on failed health check, stale/invalid feed, mismatched source/batch hash, journal write failure, duplicate/conflicting event, unexpected external network request, browser errors, security-header regression, service instability, or any execution-enabled/order-placed flag.

1. Stop only the candidate dashboard service; do not stop the canonical Gate.io market-data feeds or paper evaluator.
2. Atomically point the dashboard service to the previously recorded release and restore the previous service unit. Do not use `git reset`, `git clean`, or overwrite the existing dirty checkout.
3. Start only the previously approved read-only dashboard service.
4. Verify `/healthz`, Gate.io source identity, closed-candle freshness, `/api/journal` read-only projection, canonical journal hash continuity, no order endpoints, `execution_enabled=false`, `orders_placed=false`, and browser/API batch consistency.
5. Preserve the canonical journal and lock file; do not truncate or rewrite either during rollback.
6. Record the failed SHA, previous SHA, timestamps, service state, log excerpt, evidence hashes, and reason. Keep release status HOLD until the project owner and assistant have reviewed the failure evidence and the owner has explicitly reauthorized release.

## Recovery/fault tests required

- Feed stale/missing/corrupt/duplicate/gapped/open/future candle data must fail closed.
- Missing/unwritable journal, missing lock file, malformed JSONL, duplicate identity with conflicting content, and partial trailing record must fail closed without fabricating rows.
- Dashboard restart must not start a WebSocket collector or order path automatically.
- Simulate feed loss, dashboard process restart, journal append, repeated polling, and recovery in an isolated environment.
- Exercise rollback against a staged versioned install and prove the previous artifact hash is restored.
- Preserve the existing Gate.io 24-hour feed soak evidence, but do not treat it as a dashboard deployment/rollback test.

## Evidence ledger

- Candidate PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/398
- Exact-head CI evidence must be tied to the current PR head, not inherited from earlier candidate SHAs.
- Existing Gate.io persisted-feed soak evidence and Learning Loop journal-hash linkage are prerequisites, not production Signal→journal deployment evidence.
- Production installation and rollback, explicit owner risk approval, and verified execution instrument constraints/order lifecycle remain separate release gates. The project team is the owner and assistant; no third-party reviewer is assumed.
