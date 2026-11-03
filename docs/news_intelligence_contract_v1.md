# HES News Intelligence — v1 Runtime and Evidence Contract

**Disposition:** implementation candidates only; production is not deployed. Keep `HOLD / NO_TRADE_ONLY` until the stacked PRs pass independent review, release gates, and controlled deployment.

## 1. Role and boundaries

Qualified public news sources → existing RSS/Atom and Gate.io announcement adapters → deduplication/freshness checks → deterministic market-aware relevance/impact ranking → `hes.news_brief.v1` → durable News Monitor snapshot → read-only dashboard `/api/news` projection. Strategy Policy V2 remains the canonical decision/report path and does not consume News Radar as an execution authorization input in this release.

- Gate.io Public Spot remains the sole canonical source for live chart, candle, indicator, and market-data inputs.
- Gate.io announcements are venue-operational news only; they are not market-price or candle data.
- The exchange adapter remains execution/order-status only.
- News is evidence/context and a risk veto. It never creates LONG/SHORT, replaces the signal engine, bypasses confirmation or Risk Gate, or authorizes an order.
- Market regime is supplied by the strategy/data path. An unknown regime is not itself a news veto; news must not impersonate the regime specialist.
- No order placement, trading, collector auto-start, or deployment is part of this implementation.

## 2. Existing implementation lineage — reuse, no duplicate engine

- **PR #358:** canonical free-first `NewsIntelligenceBrain`, registry, RSS/Atom and Gate.io announcement adapters, versioned brief, and deterministic heuristics.
- **PR #399:** existing dashboard `/api/signal` integration candidate. It applies `apply_news_veto` after arbitration and before the Mother payload/journal boundary; the news payload includes provenance and veto flags. It does not create a second Mother orchestrator.
- **PR #404:** stacked Draft candidate adding continuous polling, durable source-health snapshots, read-only `/api/news`, and News Radar monitor freshness in the existing dashboard.
- **PR #359:** competing duplicate news engine; do not merge or extend it.
- PR #399 and #404 remain Draft candidates. Their ancestry must be reviewed in order; #404 is based on the #399 integration branch.

## 3. Source qualification — verified from the authorized VPS

Only sources explicitly enabled in `config/news_sources_v1.json` are fetched. Every source declares `source_scope=international|domestic|venue`; each market profile explicitly partitions `source_ids` into `international_source_ids`, `domestic_source_ids`, and `venue_source_ids`. The registry rejects missing, duplicated, or mismatched scope mappings. On 2026-10-31 each enabled feed below was checked from the authorized VPS using HTTPS with redirects rejected and XML parsed:

| Source | Result at probe | Role |
|---|---|---|
| ECB Market Information Dissemination | HTTP 200; 20 items; newest ~4.6h | Macro/regulatory |
| CFTC general press releases | HTTP 200; 10 items; newest ~61.1h | US derivatives/regulatory |
| Federal Reserve all press releases | HTTP 200; 20 items; newest ~33.6h | US central-bank policy |
| BIS media releases | HTTP 200; 10 items; newest ~54.1h | Global financial stability/regulation |
| Bank of Japan English What's New | HTTP 200; 51 items; newest ~22.1h | Central-bank/market context |
| Bank of Canada News RSS | HTTP 200; 10 items; newest ~68.3h | Central-bank/macro context |
| Gate.io official announcements | Existing documented public endpoint; existing tests and adapter | Venue-operational context |

Official RSS directories/pages:
- ECB: https://www.ecb.europa.eu/home/html/rss.en.html
- CFTC: https://www.cftc.gov/RSS/index.htm
- Federal Reserve: https://www.federalreserve.gov/feeds/feeds.htm
- BIS: https://www.bis.org/rss
- Bank of Japan: https://www.boj.or.jp/en/tips.htm
- Bank of Canada: https://www.bankofcanada.ca/rss-feeds/

**Coverage remains partial.** The crypto profile now has six official macro/regulatory/central-bank feeds plus Gate.io venue announcements. It is not a comprehensive crypto-native independent newswire. CoinDesk remains disabled because its terms restrict automated access without express written permission. Cointelegraph did not pass VPS TLS/qualification checks. The Block, Decrypt, CryptoSlate, and Kraken content are not enabled where terms prohibit automated access or require prior written permission. GDELT was not enabled because the API endpoint was not reachable from the authorized VPS during the probe. No publisher has been silently enabled on the basis of a guessed endpoint.

**Iran equities remain unqualified for domestic coverage.** No local Iranian market-news source has passed the source, terms, freshness, and VPS-reachability gates. Do not claim domestic coverage.

## 4. Intelligence and safety semantics

- Free-first Python standard library implementation; no paid news API, LLM, or extra package is required.
- Scores are deterministic heuristics, not calibrated probabilities.
- Findings retain source identity, item URL, publication time, freshness, matched terms, categories, impact/relevance scores, feed hash, and raw-item hash.
- Each configured source records `ok`, `ok_empty`, or `failed`, checked timestamp, item count, newest publication timestamp, and available feed digest. A successful empty feed is not mislabeled as a failure.
- Missing or failed source coverage is explicit and fail-closed. High-impact events, suspicious timestamps, unverified source identity, unknown schema, or incomplete source coverage can veto a directional decision.
- The news brief does not infer strategy regime. Unknown regime remains metadata for the strategy specialist and does not independently convert a clean news brief into `NO_TRADE`.

## 5. Continuous monitor candidate (PR #404)

- Starts as a worker inside the existing read-only dashboard service; no second systemd service or parallel dashboard is created.
- Immediate poll on service startup, then fixed 60-second start-to-start cadence by default (configurable 15–3600 seconds); one shared lock prevents overlapping or duplicate request-time polling.
- Persists `hes.news_monitor_snapshot.v1` atomically under `/var/lib/hes-news-monitor/news_brief_latest.json`.
- The staged `deploy/systemd/30-news-monitor-state.conf.example` drop-in adds a private `StateDirectory=hes-news-monitor` (mode `0750`) for the existing service user. The immutable release tree remains read-only.
- Snapshot integrity includes a brief digest and a full-envelope digest covering monitor metadata. Reader validates schema, digests, status, timezone-aware timestamps, future-clock tolerance, and freshness.
- `GET /api/news` is read-only. Missing, corrupt, future-dated, or stale snapshots return HTTP 503 with `fail_closed=true`, `execution_enabled=false`, and `orders_placed=false`.
- Dashboard shows monitor status, source-profile coverage, and per-source `OK / empty / failed` counts.
- This release monitors one context: crypto / BTCUSDT / Gate.io / 15m. More symbols/markets require explicit qualified context profiles; do not silently broaden the poll fan-out.

## 6. Production audit and release gates

- The active VPS release inspected on 2026-10-31 was `/opt/hes-trade-agent/releases/2e8d3859ef154b030e0965ad4479f3fad36ae4c0`; it had no News Radar/news-brain/news-monitor integration. Candidate code is not live production capability.
- The working checkout is dirty and must remain untouched: branch `feat/gateio-global-market-data-v1`, HEAD `060d0d36ae61`, 13 unstaged changes and 129 untracked paths. No reset/clean/checkout/overwrite.
- The existing `hes-readonly-dashboard.service` runs as `sentinelx` with `ProtectSystem=strict`; the news monitor state-directory drop-in is staged but not installed.
- SentinelX policy currently does not register `hes-readonly-dashboard.service` under `services:`. The operator must explicitly add only `status` and `restart` actions before this agent can manage the dashboard service through the service API. Do not edit `/etc/sentinelx/config.yaml` from the agent.
- Exact-head targeted and full repository CI must pass on the latest PR #404 head; independent review of the stacked #398 → #399 → #404 chain is required.
- Release approval is required before installing the drop-in, running `systemctl daemon-reload`, changing the release pointer, or restarting the dashboard. Verify ownership, state-directory access, artifact hash, health endpoints, rollback target, and browser/API evidence first.
- Keep execution disabled and preserve `HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY` until every release gate passes.

## 7. Delivery schedule

- Scope freeze: **2026-11-12**.
- Release candidate target: **2026-11-16**, conditional on all gates.
- Application delivery target: **2026-11-19**.

## 8. Maintenance rules

Keep source qualification, adapters, market profiles, and policy separate. Never auto-discover or scrape new publishers, never infer terms permission, never mix news with the canonical Gate.io market-data path, and never tune risk thresholds merely to make a test pass. Add a source only after official ownership, terms, HTTPS/no-redirect behavior, freshness, schema, and VPS reachability are evidenced.

## Dashboard integration status (2026-11-01)

The V2 dashboard displays the continuously monitored News Radar snapshot as context-only evidence. The legacy V1 `/api/signal` route is retired with HTTP 410; the dashboard does not poll it and it cannot write to the canonical journal. News evidence is not yet a Strategy V2 gate. Any future V2 news veto integration must be separately specified, tested against the existing Risk Gate and evaluator, and must never create a directional signal or authorize an order. Source coverage for crypto is explicitly partial: qualified international official macro/regulatory/central-bank feeds and Gate.io venue announcements; no qualified domestic source is enabled and no independent crypto-native newswire is currently qualified.

## Production News Intelligence follow-up — 2026-11-03

The existing News Radar was deployed and hardened without creating another service, VPS, market-data adapter, or trade journal.

- Current release is based on merged PRs #419, #420, #421, and #422. The single dashboard service supervises both the existing News Monitor and the new calendar fetch; trading remains OFF.
- The existing monitor now exposes per-source transport/freshness status and newest publication age. Crypto profile has nine qualified configured sources; at the 2026-11-03 production poll, all nine returned source-health rows, with eight successful and one successful-empty, zero failed.
- The first live brief contained eight findings, six high-impact source items grouped into four deterministic event clusters. These are heuristic context scores, not probabilities or directional signals. Secondary AI-summary impact is capped at 0.60 and confidence at 0.70; headline context is distinguished from headline incident claims.
- The monitor appends each source item once to `/var/lib/hes-news-monitor/news_events_YYYY.jsonl`. The annual files are append-only, hash-verified, idempotent, and include source URL/ID, publication and first-seen timestamps, raw/feed hashes, brief digest and event-cluster assignment. Corrupt records fail closed.
- `scripts/news_impact_attribution_v1.py` evaluates post-observation BTC_USDT response using only Gate.io persisted 15m candles through `global_market_data_reader_v1`. It reports 15m/1h/4h/24h return, MFE/MAE, realized volatility and volume ratio. It uses the open of the first fully post-event candle as baseline; the gap from the last pre-event close is reported separately and excluded. It does not infer causality, spread, or trade PnL.
- The dashboard now includes an official Fed event calendar over 45 days: selected Federal Reserve statistical releases plus FOMC meeting date ranges. Exact Eastern times are converted to UTC; FOMC meeting times are not guessed. The calendar is marked unrated and cannot create a signal or veto.
- BLS CPI/employment calendar remains unavailable from the VPS (HTTP 403); no bypass or unqualified third-party replacement is used. CoinDesk remains disabled pending permission; Cointelegraph remains unqualified. Decrypt's non-commercial restriction remains a deployment/usage boundary; NewsDesk AI summaries remain secondary evidence only.
- News is still context-only and is not connected as a Strategy V2/Mother veto. That connection is intentionally gated on source coverage, event-impact evidence, false-positive review, replay tests and journal attribution. No trading or Risk Gate behavior changed.
- Exact-head full repository regression: 830 passed, 70 subtests; the PR workflow matrix passed 31/31 on the event-ledger/attribution release. The Fed calendar change is separately tested and must pass its own exact-head CI before deployment.
