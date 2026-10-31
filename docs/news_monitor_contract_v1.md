# HES News Monitor v1 — Runtime Contract

**Status:** candidate implementation; not deployed until the containing dashboard release passes its approval and deployment gates.

## Purpose

Run the existing `NewsIntelligenceBrain` continuously inside the existing read-only dashboard process. This adds a scheduler and durable evidence snapshot; it does not add a second news engine, orchestrator, decision journal, or market-data source.

## Fixed boundaries

- Gate.io Public Spot remains the sole canonical source for live market data, candles, indicators and chart input.
- Gate.io announcements are consumed only as venue-operational news by the existing news engine. They are not chart or market-price data.
- The trading venue adapter remains execution/order-status only.
- News is context and a veto input. It cannot originate LONG/SHORT, override confirmation or Risk Gate, or authorize an order.
- Source coverage remains exactly what the qualified registry says. Partial coverage is shown as partial; disabled or unqualified publishers are not fetched.

## Lifecycle and polling

- The monitor starts with the existing dashboard service process and stops when that process shuts down.
- It performs one immediate poll at startup, then polls every 60 seconds by default.
- `HES_NEWS_MONITOR_INTERVAL_SECONDS` may be set from 15 to 3600 seconds.
- The same lock serializes monitor polls and request-time cache misses, preventing duplicate concurrent source fan-out.
- Existing `/api/signal` continues to use the canonical news brain and the same market-scoped brief. The monitor's cached brief is reused for the BTCUSDT/crypto/Gate.io/15m context; the strategy regime remains a separate specialist input.

## Durable evidence

Default snapshot: `/var/lib/hes-news-monitor/news_brief_latest.json`. Override with `HES_NEWS_MONITOR_SNAPSHOT`. The dashboard service template declares `StateDirectory=hes-news-monitor` (mode `0750`), preserving the read-only release tree and granting only the existing dashboard process access to its monitor state.

Each atomic snapshot contains:
- schema version `hes.news_monitor_snapshot.v1`;
- poll status, interval, last poll, last fully successful poll, and last error type;
- market/symbol/venue/timeframe context;
- the full versioned news brief, its source provenance and source failures;
- SHA-256 digest of the canonical brief JSON.

The writer uses a same-directory temporary file, flush/fsync, and atomic replace. The reader validates schema, digest, status, timezone-aware timestamp, future-clock tolerance, and maximum age.

## Health states

- `OK`: the configured sources were polled without source failures. This does **not** mean news coverage is comprehensive; the market profile still carries its qualified coverage status.
- `DEGRADED`: the poll completed but one or more configured sources failed. Failures remain visible in the brief provenance and the last fully successful poll is retained.
- `BLOCKED`: the registry, collector, or snapshot persistence failed. No fresh brief is exposed as healthy.
- A missing, corrupt, future-dated, or stale snapshot makes `GET /api/news` return HTTP 503 with `fail_closed=true`, `execution_enabled=false`, and `orders_placed=false`.

## Operational limits

This is a process-owned worker, not a separate systemd unit. It is supervised by the already-running dashboard service; systemd restart of that service restarts the monitor. It does not create new host services or widen SentinelX service policy. The snapshot directory is provisioned by systemd's `StateDirectory` mechanism; no project/release path is made writable.

The monitor is single-context in this release (crypto / BTCUSDT / Gate.io / 15m). Adding another asset or venue requires an explicit qualified market profile and context registry; do not silently broaden the source fan-out.

## Acceptance gates

1. Unit tests cover atomic snapshot creation, digest verification, source degradation, poll failure, last-success preservation, invalid interval, and future timestamps.
2. Dashboard tests cover `/api/news` success and fail-closed stale/missing snapshots.
3. CI runs Python compilation, news-brain/veto/monitor/dashboard regression, and JavaScript syntax checks on the exact branch head.
4. Full repository regression and independent review must pass after the stacked base is accepted.
5. Deployment must use the approved release pointer/rollback process. Do not mutate the dirty working checkout, activate services outside the existing dashboard process, or enable trading as part of this change.