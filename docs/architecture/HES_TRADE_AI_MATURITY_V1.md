# HES Trade AI — Architecture and Maturity Contract v1

**Date:** 2026-11-19  
**Status:** deterministic conversation core hardened in an isolated candidate; local LLM production activation remains disabled.  
**Product names:** HES Trade Agent / HES Trade AI / HES Command Center.

## 1. Responsibility boundaries

- **HES Trade Agent** is the complete product and trading system.
- **HES Trade AI** is the conversational, evidence-explanation, diagnostic and engineering-assistance layer. It works through the existing Mother Orchestrator and existing specialist/evidence readers.
- **HES Command Center** is the authenticated user interface for communication, observation, approved commands and control.

HES Trade AI is not a second Mother, a replacement for specialist agents, a signal generator, a risk approver, an execution service or an autonomous production operator.

## 2. Free-first runtime decision

The production local-LLM feature flag remains `0`. No paid API, hosted inference, remote fallback or subscription-based model is permitted. The current VPS was measured at 2 vCPU and 5.8 GiB RAM. The tested Qwen3.5-2B candidate used about 1.94 GiB RSS, generated about 3.6 tokens/s in the constrained one-thread evaluation, and required 91.768 seconds for the eight-turn test. It passed 6/8 functional turns and failed stale-data policy routing and conversation-summary routing. It is therefore not approved for production.

The production-safe baseline is the deterministic multilingual Mother Chat plus local SQLite conversation memory and the existing read-only evidence readers. The dashboard constructs this deterministic assistant even when the local-model feature flag is off; in that mode the assistant has no model client, but conversation history, contextual follow-ups, summaries and memory clearing remain available. The API reports `local_llm_enabled` separately from `conversation_memory_enabled`. If optional local-model initialization fails, the deterministic memory-backed assistant remains available. A future model may be reconsidered only after a separate resource/quality evaluation and must remain a non-authoritative presenter/router behind the same contracts. No model may access tools, secrets, exchange APIs, arbitrary files, order routes or production-write permissions.

## 3. Conversation and memory contract

- Languages: Persian, English, German and French; Persian responses use RTL.
- Deterministic routing is preferred for known HES intents and common follow-ups. Ambiguous or unsupported requests ask for clarification; they do not trigger speculative evidence reads.
- HES facts are returned only by the existing typed readers. Every answer preserves source status, reason codes, evidence references and uncertainty. Missing data remains missing; `PARTIAL`/`BLOCKED` cannot be upgraded to `OK` by a presenter.
- Conversation memory is local SQLite, single-owner, 30-day retention, at most 200 messages, authenticated history and explicit clear-memory control. The ordinary routing context is limited to the latest eight messages.
- Conversation-summary requests read the bounded retained history (up to 200 messages) and return an extractive review of the latest eight complete turns. The output states how many turns are shown and how many were stored. It does not claim to regenerate live HES facts or infer unstored details.
- Project memory is a separate read-only retrieval path over explicitly approved local Markdown roots. Every returned excerpt must carry provenance/hash metadata. Notion-only content is not represented as locally available unless an approved connector is actually wired and verified.

## 4. Evidence and capability layers

1. **Conversation:** intent, language, follow-up resolution, session continuity and user-controlled memory.
2. **Project memory:** approved checkpoint/architecture retrieval with source references.
3. **Operational intelligence:** read-only status, service health, API/CI/log diagnostics and incident explanation.
4. **Trading intelligence:** read-only explanation of Mother/specialist outputs, market-data quality, regime, strategy gates, journal outcomes and news context. The canonical Gate.io feed and existing Mother outputs remain the source of truth.
5. **Research/hypothesis support:** prepare reproducible hypotheses and compare baseline/candidate evidence in isolated worktrees; no live threshold mutation or hindsight tuning.
6. **Engineering copilot:** produce a minimal patch proposal, tests, security review, provenance and rollback plan. Production mutation requires approval of the exact diff and target.

These layers are capabilities over existing HES components, not permission to create parallel readers, duplicated data stores or alternate trading logic.

## 5. Safety invariants

Every response must preserve these explicit false values unless a separately reviewed product contract changes them: `external_llm_used`, `execution_enabled`, `orders_placed`, `journal_write`, and `policy_mutation`. HES Trade AI never receives an exchange credential or direct order capability. It cannot approve risk, bypass Mother gates, create a trade signal, mutate a strategy, merge code or deploy. Prompt injection cannot expand the fixed intent allowlist or tool surface.

## 6. Promotion gates

A capability is not mature merely because a unit test passes. Promotion requires:

- reproducible Persian/English/German/French evaluation with realistic multi-turn sequences;
- exact evidence provenance, claim/status preservation and explicit uncertainty;
- long-dialogue and follow-up tests, including 16-message/8-turn memory summaries;
- bounded latency and resource use under the normal HES service load;
- authentication, rate-limit, session-isolation, memory-clear/retention and filesystem-boundary tests;
- prompt-injection and read-only invariant tests;
- exact-head CI, reviewed diff, release manifest, rollback plan and separate owner approval before production changes.

A synthetic fixture pass is not live-market acceptance. A local model smoke test is not permission to enable it in production.
