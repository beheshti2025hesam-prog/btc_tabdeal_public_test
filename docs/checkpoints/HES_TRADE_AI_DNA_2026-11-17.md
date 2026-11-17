# HES Trade AI — Canonical Project DNA Snapshot

- Source: Notion page **HES Trade AI — Local Private AI Environment — DNA & Roadmap — 2026-11-17**
- Source URL: https://app.notion.com/p/41b0a937939181bcae32e628746b1324
- Source last edited: 2026-11-17T11:43:01Z
- Source verification metadata: `unverified`
- Related Master Checkpoint: https://app.notion.com/p/3f80a937939181619f0fce6b19b968d0
- Snapshot purpose: bounded, read-only local retrieval; refresh when the canonical Notion page changes. This is not a live Notion connection.

## Official product naming — approved 2026-11-17

- **HES Trade Agent:** the complete product and trading-agent system.
- **HES Trade AI:** the intelligent brain and conversational assistant, working with the existing Mother Orchestrator and specialist agents.
- **HES Command Center:** the user-facing interface for communication, observation, commands and control.
- **HOSHYAR is retired as a user-facing product name.** Existing internal identifiers containing `hoshyar` or `HOSHYAR` (module/class names, schema IDs, environment variables, systemd unit names, filesystem paths, API-key filenames and model labels) remain unchanged for now. Do not perform a global rename. Any later technical migration requires separate review, tests, backward compatibility and an approved isolated release.

## Non-negotiable architecture and safety boundaries

- Free-first, local/open-weight model runtime and free/open components. No paid LLM API, subscription, metered inference, hosted model or remote LLM fallback.
- Core runtime, orchestration, memory and retrieval remain on the existing HES VPS. Browser/mobile clients remain thin; no model download or inference on the client is required.
- Reuse the existing Mother Orchestrator, multilingual chat, specialist agents, journal, Learning Loop, Gate.io reader, APIs, authentication and dashboard. Do not create a parallel orchestration stack without evidence that it is necessary.
- Mother evidence readers remain authoritative for HES facts. The local model may route bounded intents and handle ordinary conversation; it is not a substitute for specialist agents, not a trading decision authority, not an autonomous coder and not an autonomous trader.
- No bypass of Data Quality, Confirmation, Risk Gate, `NO_TRADE`, human approval or execution controls. Read-only by default; least privilege for every tool adapter.
- Diagnose, reason, propose and run isolated experiments; never mutate production code, strategy/risk policy, deploy or execute trades without explicit, specific approval. Every claim requires evidence, tests, metrics and stated limitations.

## Product capabilities and roadmap

1. Natural multilingual conversation, initially Persian, English, German and French; multi-turn context, references, clarification and session continuity.
2. Durable controlled memory separating session context, verified project facts, preferences and experimental notes, with retrieval provenance and user control.
3. Evidence-based diagnostics across logs, reports, services, APIs, CI and code.
4. Strategy analysis and learning from accepted/rejected decisions, gate attribution, missed opportunities and resolved outcomes using canonical journals; no hindsight leakage or metric manipulation.
5. A hypothesis lab with explicit measurable criteria, reproducible isolated worktrees/sandboxes, baseline/candidate comparison and out-of-sample/cost/slippage checks.
6. Human-approved engineering: minimal patches, tests, security review, provenance, explicit approval, controlled deployment and rollback.

## Implementation phases

- **Phase 0 — Inventory and feasibility:** inspect the sole VPS, services, Mother/chat, dependencies, security boundaries and dirty checkout. Never reset/clean the checkout or restart unrelated services.
- **Phase 1 — Local model benchmark:** measure CPU/RAM, latency, context, multilingual quality and concurrent-load impact. If resources or quality are insufficient, report the constraint; never fall back to paid/remote inference.
- **Phase 2 — Conversation and memory:** extend existing Mother chat for multilingual multi-turn context, session isolation, durable memory, retrieval and grounded citations.
- **Phase 3 — Diagnostics and strategy intelligence:** read-only evidence-linked explanations over operational and trading records.
- **Phase 4 — Hypothesis lab:** reproducible isolated experiments, baselines, metrics, out-of-sample validation and signed artifacts.
- **Phase 5 — Engineering copilot under approval:** patch proposal, tests, review, approval, controlled deployment and rollback.

## 2026-11-17 measured candidate and staging status

- VPS: 2 vCPU, x86_64 Broadwell-class, 5.8 GiB RAM, 2 GiB swap, no NVIDIA GPU.
- Selected MVP candidate: Qwen3.5-2B Q4_K_M, open-weight Apache-2.0 per upstream model card; model card states 201 languages/dialects.
- CPU-only llama.cpp: approximately 3.7–3.8 generated tokens/s at one thread and approximately 7 tokens/s at two threads; prompt evaluation approximately 19 tokens/s; model RSS approximately 2.1 GiB. During observed tests with HES services active, approximately 4.1–4.4 GiB RAM remained available. These are point-in-time measurements, not a long-duration concurrency guarantee.
- Selected model artifact SHA-256: `cd1950c433492e0bbf2e64f32486c525af0e0bf2ab98dd73c329e597ef282f2d`. Model artifact stays outside Git.
- Local adapter uses only loopback inference, bounded JSON intent routing and the existing Mother read-only evidence readers. No remote/paid fallback, tool calls, exchange credentials, order route or production-write permission.
- Local SQLite conversation memory: 30-day retention, 200-message cap, last eight messages as model context, authenticated history and explicit clear-memory action.
- 2026-11-17 staging result: `STAGING_PASS / PRODUCTION_NOT_ENABLED`. No model systemd unit installed/enabled, no API key provisioned for production, no dashboard feature flag enabled, no production service restarted and no release pointer changed.

## Local retrieval boundary

This snapshot is copied from the canonical Notion DNA page into the VPS repository for local read-only retrieval. The current reader searches only approved local Markdown roots (`docs/checkpoints`, `docs/architecture`, `releases/deployment-records`) and returns excerpts with SHA-256 references. It does not access Notion-only pages, connected accounts, private files or secrets. Refresh this snapshot from Notion when the canonical page changes; do not imply that the VPS has live Notion access.
