# Mother Chat / Command Center — Architecture Contract
**Date:** 2026-11-06  
**Status:** DESIGN LOCKED; APPLICATION CHAT NOT IMPLEMENTED  
**Target delivery:** 2026-11-19  
**Scope:** The existing HES Trade Agent application, its existing dashboard and Mother Orchestrator. This is an incremental integration contract, not approval to replace the dashboard or create a second application.

## 1. Verified current state

The active application already has a deterministic, read-only Mother Orchestrator and a dashboard panel for it. Reuse these components:

- `core/orchestration/mother_v1.py` and `mother_contract_v1.json`: bounded stage sequencing, specialist-result validation, evidence provenance, veto handling, trace/audit hash and an unconditional `execution_authorized=false` boundary.
- `web/mother_v2_dashboard_view.py`: reads the existing Strategy V2 report and the exact matching immutable journal event; does not recalculate market data, indicators, strategy, risk or outcomes.
- `GET /api/mother`: current read-only Mother projection.
- Existing Strategy V2, Gate.io reader, News Radar, Precision Entry, journal and dashboard sections.

The following absence was verified in the active immutable release `3c8460efd3a8bf6dd5facd6e9b6cc6ff19a487d0`:

- No chat panel, conversation endpoint, prompt router, or persisted chat-session implementation was found.
- The dashboard's `do_POST` handler returns HTTP 405 for every POST; there is no message-submit API.
- No OpenAI, Anthropic, Ollama, LiteLLM or other LLM SDK/provider configuration was found in application dependencies or source.
- The dashboard is intentionally read-only and loopback-bound. It has no authenticated chat session or CSRF boundary because it currently accepts no writes.

Therefore the Mother brain exists as a deterministic orchestrator, but a natural-language chat interface connected to it does not yet exist. Do not represent this section as complete until the chat path is implemented and verified.

## 2. Architectural decision

**Use one conversational interface over the existing Mother and existing application services. Do not create a second brain, strategy engine, journal, market-data path, or parallel frontend.**

The LLM, when configured, is a language and explanation layer only:

1. Understand the user's Persian/English/German/French message and classify it into a small, versioned intent schema.
2. Ask the deterministic backend for approved, typed evidence through existing read interfaces.
3. Explain the returned facts, uncertainty, gate reasons and provenance in natural language.
4. Preserve conversation context without treating memory as live market truth or authorization.

The deterministic application remains the authority for market data, strategy, Risk Gate, Mother state, paper outcomes and all side effects. The LLM must never calculate or override those values.

### Canonical data and action boundaries

- Live candles, chart and indicators: Gate.io Public Spot `BTC_USDT`, through the existing `global_market_data_reader_v1` path only.
- Mother: consumes existing Strategy V2 and matching journal evidence; no duplicate indicator/strategy/risk calculations.
- News: contextual evidence only; it cannot originate a direction or authorize a trade.
- Execution: separate exchange/broker application; chat has no order-submit tool or account credentials.
- Paper-signal ceiling: at most three actionable candidates per day, a ceiling rather than a quota. The >90% paper win-rate objective remains unproven and must be measured from resolved, cost-aware, out-of-sample outcomes.

## 3. User-visible chat capabilities (first release)

| Intent | Behavior | Permitted data/action |
|---|---|---|
| `ASK_STATUS` | Explain current app, feed, service and gate status | Read-only existing status APIs |
| `EXPLAIN_DECISION` | Explain why Mother/Strategy chose LONG, SHORT or NO_TRADE | Exact report, Mother trace, gate reasons and journal refs |
| `MARKET_REVIEW` | Summarize the latest validated closed-candle context | Existing Gate.io reader outputs only |
| `JOURNAL_REVIEW` | Explain decisions and matured outcomes | Existing append-only journal and evaluation outputs |
| `NEWS_CONTEXT` | Summarize verified news context and source freshness | Existing News Radar snapshot |
| `DIAGNOSE` | Explain a reported application fault | Read-only health and diagnostic tools |
| `PREPARE_CHANGE` | Draft a bounded change proposal or PR description | No write or deploy until a separate approval flow exists |

Unsupported or ambiguous requests must be clarified or declined. The chat must explicitly state when a value is unavailable, stale, unverified, or outside the recorded evidence. It must never invent a signal to satisfy a request.

## 4. Request pipeline

`Browser Chat UI → authenticated session boundary → Chat API → intent/schema validator → deterministic policy router → existing read adapters → evidence envelope → LLM response formatter → UI`

- The LLM proposes only a typed intent and bounded arguments. The backend validates them independently; free-form model text is never interpreted as a shell command, SQL, Python, URL fetch instruction or tool name.
- The policy router maps each accepted intent to a fixed allowlist of existing read functions. No arbitrary tool discovery or model-selected executable is permitted.
- Retrieved pages, news, journal text, user-provided prompts and tool outputs are untrusted data, never system instructions. Prompt injection inside those sources cannot expand permissions.
- Every answer carries a compact evidence footer: data source, symbol/timeframe, observed-at time, report/journal reference, freshness and Mother trace where applicable.
- If an existing read API fails or provenance does not match, the answer is a blocked/unknown response; no stale cached value or alternate market-data source is silently substituted.

## 5. Prompt hierarchy and versioning

Keep a small immutable policy prompt and separate versioned task templates:

1. **System policy:** product identity, truthfulness, source hierarchy, safety invariants, language and refusal rules.
2. **Application contract:** typed intents, available read tools, evidence format, output schema and hard limits.
3. **Task template:** status, decision explanation, market review, journal review, news context or diagnostics.
4. **User message:** untrusted request text; cannot override layers 1–3.
5. **Retrieved evidence:** explicitly delimited untrusted records with provenance.

Every prompt/template has an ID, semantic version, content hash, effective date and regression fixtures. Prompt changes are reviewed like code. No prompt may modify strategy thresholds, risk limits, signal cap, execution permission, market-data source or policy lock. User-authored prompts can set the question and preferred explanation style, not system policy.

The response contract should be structured before rendering:
- `answer`
- `intent`
- `status` (`OK`, `PARTIAL`, `BLOCKED`, `NEEDS_CLARIFICATION`)
- `claims[]` with evidence references
- `uncertainties[]`
- `actions_proposed[]` (display-only in this release)
- `trace_id`, `prompt_version`, `model_id`

Reject malformed output and fall back to a deterministic status/error response.

## 6. Session, memory and audit

Keep state classes separate:

- **Conversation transcript:** user/assistant messages, session ID, timestamps and retention policy; not authoritative project state.
- **Turn context:** only the bounded recent turns needed for the current answer.
- **Project checkpoint:** existing Master Checkpoint / GitHub evidence; never replaced by free-form chat memory.
- **Live truth:** current API/service/journal response with observation time; always re-read for live questions.
- **User preferences:** language and explanation style only; never permissions, secrets or trade authorization.

Each request gets a UUID request/trace ID and idempotency key. Persist prompt version/hash, provider/model ID, intent, bounded tool calls, evidence references/hashes, response status, latency and redacted error class. Never log API keys, cookies, auth tokens or raw secrets. Resume must reject expired sessions, duplicate writes and stale approvals.

## 7. Security and permission model

The existing dashboard's loopback-only binding is necessary but not sufficient for a writable chat API.

Before enabling message POST:
- Add an authenticated, expiring, single-user session mechanism suitable for the existing SSH-tunnel access pattern; keep secrets outside source control and outside the journal.
- Enforce same-origin checks, CSRF protection, strict JSON content type, body-size and message-length limits, request rate limits, session expiry and secure cookie settings.
- Keep the API loopback-bound; do not expose port 8765 publicly or relax CSP to arbitrary external origins.
- Use a provider adapter with server-side credentials only. No browser-side provider key, account credential, or direct browser-to-exchange request.
- Use fixed read-only tool allowlists. The model cannot invoke shell, filesystem, Git, deployment, service-control, account, broker or exchange-order tools.
- Do not add a chat write path to the canonical journal. Chat transcript storage is separate and cannot mutate decision records.

### Side-effect policy

| Class | First-release policy |
|---|---|
| Read market/strategy/Mother/journal/news/status | Allowed through fixed backend adapters |
| Draft explanation, prompt or change proposal | Allowed; clearly marked as draft |
| Change strategy, thresholds, risk, source, signal cap or policy | Denied from chat |
| Write journal/outcomes or alter evidence | Denied from chat |
| Git commit/merge, deploy, service restart, VPS mutation | Not exposed as chat tools |
| Exchange/broker account access or order placement | Never exposed to chat |

A future consequential-action workflow, if separately approved, must use preview → exact action/target/parameter hash → explicit user approval → short expiry → idempotent execution → independent verification. Approval for one action must not authorize a changed action.

## 8. Provider adapter and deployment prerequisites

Implement a provider-neutral server adapter, but enable only one selected provider in a deployment. Provider choice and API credentials are not present in the verified current app. No key or provider is assumed.

- Read provider/model/base URL and secret reference from protected server configuration.
- Fail startup or report `CHAT_PROVIDER_NOT_CONFIGURED` when mandatory configuration is absent; never fake an AI response.
- Apply bounded timeouts, token/context limits, concurrency limits and cost ceilings.
- Retry only transient, idempotent model requests with a small bounded retry count; never retry a side effect.
- Redact provider errors and secrets from user output and logs.
- Keep a deterministic no-provider mode for health/status and explain that natural-language chat is unavailable until configuration is complete.

No provider key is to be pasted into chat, committed to Git, stored in Notion, or written into the project journal.

## 9. Acceptance gates before calling chat complete

1. Existing dashboard/Mother/Strategy V2 and Gate.io single-source tests remain green; no existing behavior is duplicated or weakened.
2. A user can submit a Persian, English, German or French message and receive a response tied to real, fresh evidence.
3. Every intent is schema-validated and maps only to its fixed read adapter.
4. Mother and Strategy decision explanations reproduce exact stored state/reason codes; no generated directional claim can contradict the report.
5. Stale/missing/mismatched Gate.io batches, journal events, Mother witness, or news evidence produce explicit BLOCKED/PARTIAL answers.
6. Prompt injection in user text, news, journal, web content and retrieved documents cannot call tools or change policy.
7. Unauthorized origin, missing/expired session, CSRF, oversized body, rate-limit breach and malformed JSON are rejected.
8. Provider timeout, rate limit, invalid structured output and unavailable provider produce safe deterministic fallback responses.
9. Transcript/session state is isolated from the canonical trade journal and project checkpoint.
10. Browser tests cover desktop/mobile, keyboard/accessibility, RTL Persian and all supported locales.
11. Regression tests prove chat cannot change strategy/risk configuration, exceed the three-candidate ceiling, write a journal decision, access credentials, deploy, restart services or submit orders.
12. Deployment is an atomic, rollback-capable release on the sole VPS; no dirty checkout reset or parallel app.

## 10. Delivery sequence and current blockers

- **By 2026-11-12 — scope freeze:** settle provider choice/configuration method and finalize the chat API/session contract.
- **By 2026-11-16 — release-candidate gate:** implementation, security tests, provider failure tests, browser/mobile/RTL tests and evidence-linked answer tests pass on the exact candidate SHA.
- **2026-11-19 — delivery:** chat is enabled only if all gates pass; otherwise ship the existing read-only dashboard honestly and mark chat as a documented deferred capability rather than a fake/unsafe feature.

Current verified blockers:
1. No chat UI or message endpoint exists in the active application.
2. No model provider adapter or provider configuration exists.
3. No authenticated chat session / CSRF boundary exists.
4. The dashboard POST path is intentionally HTTP 405; it must not be opened casually.

**Next implementation slice:** add the chat panel to the existing dashboard and a separate, authenticated chat endpoint; implement typed intent validation and fixed read-only adapters that call existing Mother/Strategy/Market/Journal/News readers. Keep the current `GET /api/mother` contract unchanged. Implement against a new isolated branch/release candidate, with exact-SHA tests and rollback. Do not edit the active immutable release or the dirty working checkout.

## 11. Non-goals

No new trading strategy, signal generator, market-data adapter, journal, multi-agent swarm, autonomous shell agent, exchange account integration, order execution, public dashboard exposure, or second VPS. No claim of 90% win rate or profitability is made by chat readiness.
