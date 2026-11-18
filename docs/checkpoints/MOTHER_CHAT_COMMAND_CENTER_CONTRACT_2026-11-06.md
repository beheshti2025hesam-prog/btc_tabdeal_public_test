# HES Trade Agent — Multi-Agent / Mother Command Center
**Checkpoint date:** 2026-11-06  
**Status:** EXISTING MOTHER ORCHESTRATOR VERIFIED; FREE COMMAND CENTER IMPLEMENTED IN DRAFT PR; NOT YET DEPLOYED  
**Delivery target:** 2026-11-19  
**Scope:** Incremental integration into the existing HES dashboard on the sole VPS. No second application, VPS, strategy engine, market-data reader, journal or execution path.

## 1. Existing architecture — reuse, do not rebuild

The active release already contains the deterministic Mother architecture:

- \`core/orchestration/mother_v1.py\` and \`mother_contract_v1.json\`: fixed seven-stage sequence, strict specialist contracts, provenance validation, fail-closed veto handling, same-snapshot directional coherence, deterministic trace/audit hash, and unconditional \`execution_authorized=false\`.
- Required stage order: \`data_quality → market_structure → signal → confirmation → risk → decision → evaluation\`.
- \`PrecomputedSpecialistV1\` adapts the existing Strategy V2 report. It does not launch duplicate indicator, strategy, risk, learning or execution agents.
- \`core/orchestration/witness_v1.py\`: independently verifies the serialized Mother audit envelope and its safety invariants.
- \`web/mother_v2_dashboard_view.py\`: binds the exact Strategy V2 report to its matching immutable journal event and existing market-data provenance.
- \`GET /api/mother\`: the existing read-only Mother projection and dashboard panel.

This is a deterministic specialist pipeline, not an autonomous LLM swarm. That is intentional: specialist work remains owned by existing, tested components; Mother coordinates and verifies their outputs. Do not add parallel agents that recalculate the same market, signal, risk or outcome facts.

\`forward/agent_disagreement_resolver_v1.py\` is a separate arbitration utility, not the active Mother authority. Do not bolt it into the active path without a demonstrated gap and a same-snapshot integration proof.

The \`evaluation\` stage in Mother means decision-observation validation. Realized performance remains in the separate forward paper-outcome/evaluation pipeline.

## 2. Canonical data and safety boundaries

- Live candles, chart and indicators: Gate.io Public Spot \`BTC_USDT\` through the existing \`global_market_data_reader_v1\` path only.
- Mother consumes Strategy V2, its matching immutable journal event and the exact evidence hashes; it does not fetch a second market source or recompute strategy/risk.
- News is contextual evidence only; it cannot originate direction or authorize a trade.
- Execution remains separate in the exchange/broker application. The dashboard and Command Center have no account credentials, order-submit tools or execution adapter.
- Maximum three actionable paper candidates per day is a ceiling, not a quota.
- The >90% paper win-rate objective is not proven. It must be assessed from a sufficiently large, resolved, cost-aware and out-of-sample paper cohort. Chat readiness is not trading-performance evidence.

## 3. Free Command Center — implementation choice

The user's standing constraint is that the user-to-Mother interface must use free capabilities; no paid API or paid model is permitted for this layer.

The first implementation therefore uses a **deterministic local intent router and evidence formatter**, not an external LLM:

- No OpenAI, Anthropic, hosted model, paid API, browser-side key or model SDK is called.
- No LLM is installed or required on the VPS.
- Supported intents are explicitly bounded: \`ASK_STATUS\`, \`EXPLAIN_DECISION\`, \`MARKET_REVIEW\`, \`JOURNAL_REVIEW\`, \`NEWS_CONTEXT\`, \`DIAGNOSE\`, and clarification-only \`PREPARE_CHANGE\`.
- Persian, English, German and French intent terms and answer templates are supported. Ambiguous or unsupported requests return \`NEEDS_CLARIFICATION\`; the router does not invent a signal or improvise a tool.
- The router calls only the fixed existing readers for Mother/Strategy, Gate.io closed candles, journal, News Radar and read-only diagnostics.
- Claims are returned with their evidence references, uncertainty, trace ID and explicit read-only flags.
- No chat transcript is stored server-side. The visible message history exists only in the current page and disappears on reload.

This is a bounded Command Center, not a general-purpose chatbot. A future local open-source model may be considered only if it remains free, fits the sole VPS resource envelope, and passes separate privacy, latency, prompt-injection and evidence-grounding gates. It is not a delivery dependency.

## 4. Request path and routes

\`Dashboard UI → same-origin session boundary → bounded message parser → fixed intent allowlist → existing evidence readers → structured evidence response → UI\`

New endpoints on the draft branch:

- \`POST /api/mother-chat/session\`: verifies the local operator token and issues a short-lived signed session cookie.
- \`POST /api/mother-chat\`: accepts only a bounded \`{"message": "..."}\` JSON object and one of the fixed read-only intents.
- \`POST /api/mother-chat/logout\`: expires the session cookie.
- Unknown POST paths continue to return HTTP 405.
- Existing \`GET /api/mother\`, Strategy V2, candle, journal and news routes remain unchanged.

The response schema includes \`schema_version\`, \`router_version\`, \`intent\`, \`status\`, \`answer\`, \`claims[]\`, \`uncertainties[]\`, \`evidence_refs[]\`, \`trace_id\`, observation time and explicit \`external_llm_used=false\`, \`execution_enabled=false\`, \`orders_placed=false\`, \`journal_write=false\`, and \`policy_mutation=false\`.

## 5. Authentication and security

The dashboard remains loopback-only; do not expose port 8765 publicly.

- Local token file default: \`/var/lib/hes-news-monitor/mother-chat/token\`.
- The token file must be owned by the dashboard service user and have mode \`0600\` (no group/world permissions); token length is at least 32 characters.
- Login issues a signed, HttpOnly, SameSite=Strict cookie with a 30-minute expiry. The browser never stores the token in local/session storage and clears the password field after login.
- All chat POST routes require exact same-origin validation; cross-site requests are rejected.
- JSON content type, exact payload keys, body size, message length, login attempts and request rate are bounded.
- No arbitrary tool discovery, shell, filesystem, Git, service-control, deployment, account, broker, exchange or order action is exposed.
- No chat write path is connected to the canonical journal or strategy policy.
- Errors are reduced to safe reason codes; raw secrets and exception details are not returned.

If the token file is absent or has unsafe permissions, chat login returns a blocked configuration response. No default password is embedded in source.

## 6. Current implementation evidence

Draft PR: [#468 — Mother Command Center](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/468)

Files added/updated on the draft branch:

- \`web/mother_chat_v1.py\`: deterministic intent routing, four-locale evidence responses, token-file validation, signed sessions, origin checks, rate limiting and bounded JSON parsing.
- \`web/dashboard.py\`: fixed read-only evidence readers and three exact POST routes; unknown POST paths retain HTTP 405.
- \`web/static/dashboard.js\`: Command Center login/chat/lock interaction; token is not persisted by the browser; all untrusted text is rendered with \`textContent\`.
- \`web/static/dashboard.css\`: responsive chat presentation.
- \`tests/test_mother_chat_v1.py\`: parser, localization, evidence failure, session, file permissions/symlink rejection, origin, rate limit, body validation, prompt-injection and HTTP/UI boundary tests.
- \`scripts/test_native_ohlcv_dashboard_browser_smoke.cjs\` and \`.github/workflows/native-ohlcv-browser-render-smoke-v1.yml\`: actual Chromium login/chat/logout, Persian RTL heading, 390px mobile layout and chart parity smoke. The workflow creates an ephemeral test-only token; no production secret is used.

Exact candidate head: \`880a60e494ab3ab682718dcfad95dced84e79f62\`.

Verification on this exact candidate:

- Canonical offline regression gate: **1,127 passed; 82 subtests passed**; warnings treated as errors; bytecode/compile gate passed.
- GitHub Actions: **32/32 workflows succeeded**, zero failed. This includes HES Full Regression Gate, Gate.io Dashboard Full Repository Regression, Native OHLCV Dashboard Single Path, Native OHLCV Browser Render Smoke, Gate.io Public Candle Evidence Smoke, Forward Integration Verification and Clean Forward Evidence Verification.
- Browser artifact for exact head \`880a60e4...\`: artifact ID \`13489898242\`, SHA-256 \`ac3320a6483e2876ec3083089bae9cd080cfe1d31d8ef68b5e62ed2c1816fd5c\`. The browser smoke passed actual token login, unsupported-intent clarification, logout, Persian RTL heading and mobile layout, alongside existing 15m/1m chart parity checks.
- Live read-only smoke with production data paths: Gate.io 15m feed **OK**; Strategy V2 **VERIFIED**; Mother **BLOCKED_GATE / NO_TRADE**; independent Mother witness **VERIFIED**; decision journal **VERIFIED**; News Radar transport **OK** with incomplete source coverage.
- Current Mother attribution: \`NO_VALID_CANDIDATE\`; confirmation is \`UNCONFIRMED\`. Signal reasons include \`NO_CONFIRMED_20_BAR_BREAKOUT\`, \`PRICE_NOT_ALIGNED_WITH_EMA50_AND_VWAP\`, and \`MOMENTUM_OR_FLOW_NOT_CONFIRMED\`. This is a valid fail-closed NO_TRADE decision, not a witness failure.
- All six live read-only intents were exercised. Status, decision explanation and diagnostics return \`PARTIAL\` while the current Mother gate is blocked; market and journal summaries return \`OK\`; News returns \`PARTIAL\` because source coverage is incomplete.
- A production token was staged at \`/var/lib/hes-news-monitor/mother-chat/token\`, owned by the dashboard service user, mode \`0600\`, inside a dedicated mode-\`0700\` subdirectory under the existing \`StateDirectory=hes-news-monitor\`. It is not in Git and is not active in the deployed application yet.
- No production deployment, service restart, market-data change, journal write, policy change or order action was performed. The Command Center remains disabled in production until the candidate is accepted and the controlled release gate is approved.

The deployed immutable release remains \`3c8460efd3a8bf6dd5facd6e9b6cc6ff19a487d0\`. The active release pointer, market-data services, canonical journal, policy and dirty original checkout were not changed by this implementation work.

## 7. Acceptance gates

1. Full repository regression passes on the exact candidate SHA; existing Mother, Strategy V2, Gate.io, journal and dashboard tests remain green.
2. Persian, English, German and French supported intents return evidence-linked answers; unsupported/ambiguous inputs request clarification.
3. Mother/Strategy status, decision and reason codes match the exact stored report/journal evidence; no generated direction is introduced.
4. Stale, missing, gapped or mismatched market evidence fails closed; the chat never substitutes another source.
5. Journal and news responses state partial/unknown coverage and never infer outcomes or market direction.
6. Missing/unsafe token file, bad credentials, expired session, cross-origin POST, malformed JSON, oversized body, excessive length and rate-limit breach are rejected.
7. Prompt-like user text, news and journal content cannot expand the fixed reader allowlist or change application policy.
8. Browser tests cover desktop/mobile, keyboard/accessibility, RTL Persian and the four UI locales.
9. Regression proves no order, account access, journal write, policy mutation, Git/deploy/service action or public bind is reachable from chat.
10. Candidate deploy is atomic and rollback-capable on the sole VPS. The original dirty checkout and active immutable release must not be edited in place.

## 8. Delivery controls

- **2026-11-12:** scope freeze / go-no-go.
- **2026-11-16:** release-candidate gate, including exact-SHA regression and browser/security evidence.
- **2026-11-19:** fixed delivery target.

If the Command Center misses a security or acceptance gate, deliver the existing read-only dashboard honestly and keep chat disabled. Do not weaken authentication or evidence gates to meet the date.

## 9. Non-goals

No second Mother brain, duplicate strategy/risk/market-data engine, parallel frontend, paid LLM/API, autonomous shell agent, self-authorizing policy mutation, exchange account integration, order execution, public dashboard exposure or second VPS. No claim of 90% win rate or profitability is made by this work.


## 2026-11-06 deployment update — PR #468 is live on the sole VPS

- PR #468 merged into `main` as `786f9187ac326f27c243507ccbd297b34d01db1b`.
- Immutable release: `/opt/hes-trade-agent/releases/786f9187ac326f27c243507ccbd297b34d01db1b`; archive SHA-256 `ab1a68531a3469270ec9fea6ebe5617226a2998b07539d199af1618220e5e65c`.
- The merge tree differs from exact CI-tested candidate `880a60e494ab3ab682718dcfad95dced84e79f62` only in this checkpoint document; all non-checkpoint files are identical. The tested candidate had 32/32 workflows pass, including browser render and full regression. A clean local clone of the merge commit passed 1,127 tests + 82 subtests; compile and pip checks passed.
- Previous active release: `3c8460efd3a8bf6dd5facd6e9b6cc6ff19a487d0`. New `current` pointer atomically targets the new immutable release. Previous dashboard unit/drop-ins backed up under `releases/rollback-dashboard-before-786f9187ac32/`. Atomic pointer rollback simulation passed.
- Only `hes-readonly-dashboard.service` was restarted. It is active with zero systemd restart failures. The original dirty checkout was preserved; no reset, clean, checkout, or overwrite.
- Post-deploy: health and read-only APIs returned HTTP 200; 1m/15m/1h/4h each returned 240 Gate.io public Spot BTC_USDT candles. Security headers passed. Unauthenticated chat returned 401; journal POST returned 405. Seven-sample / 64-second read-only soak passed with zero service restarts and unchanged journal SHA-256 `a7bc4dcfe2e0378ac8f9ac6e931f2818ffc57c4c000880ced0169c0bb0287596`.
- Mother remains `BLOCKED_GATE / NO_TRADE`; Strategy V2 is `VERIFIED`; execution and orders remain disabled. This is not proof of a >90% win rate or permission for live trading.
- Production token remains outside Git at `/var/lib/hes-news-monitor/mother-chat/token`, service owner, mode `0600`, parent mode `0700`.
- Browser CI exercised login/chat/logout with an ephemeral token on the byte-identical code tree. The VPS did not have Playwright installed, so no extra on-host browser automation is claimed.
