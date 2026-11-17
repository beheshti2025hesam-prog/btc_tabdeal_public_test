# HES Trade AI — Local Private AI Environment v1

**Decision date:** 2026-11-17
**Architecture:** lightweight VPS-first local AI with a thin web client
**Implementation state:** isolated staging pass; production activation remains disabled pending exact-change approval.

## Product DNA

The canonical Notion DNA approved 2026-11-17 names the user-facing brain **HES Trade AI** and the UI **HES Command Center**. `HOSHYAR` remains only in existing internal identifiers for backward compatibility; no global rename is permitted.

HES Trade AI is the dedicated, private AI environment of HES Trade Agent. It is not a paid AI gateway and must not forward prompts to ChatGPT, Grok, hosted inference providers or other external LLM APIs. The model runtime, orchestration adapter and conversation memory live on the HES VPS. The browser/mobile interface remains thin and does not download or run a model.

The local model is a conversational and language-understanding layer—not a replacement for HES's deterministic specialist agents. Existing Mother readers remain the source of truth for HES status, market data, strategy decisions, journal, news and diagnostics. The local model may select only a fixed allowlist of read-only intents and handle ordinary conversation. It receives no tools, exchange credentials, account access, order routes, production-write permissions or external network access.

## VPS feasibility snapshot

Read-only host inspection on 2026-11-17:

- x86_64, 2 vCPU (Intel Broadwell-class), no NVIDIA GPU detected.
- RAM: 5.8 GiB total; approximately 4.4–4.5 GiB available during the benchmark observations.
- Swap: 2 GiB.
- Root disk: 50 GiB total, approximately 22 GiB free before model downloads.
- HES services remained active during the local inference tests. The model process was deliberately run with low priority; no production HES service was restarted or modified.

## Model comparison and selection

| Candidate | Quantization / footprint | Result |
|---|---|---|
| Qwen3.5 0.8B | Q4_0, approximately 0.54 GB | Rejected as the primary assistant candidate: too small for reliable instruction-following and multi-turn HES interaction. |
| Gemma 3 1B IT | Q4_K_M, approximately 0.8 GB | Rejected: Persian instruction/safety behavior did not meet the required bar in the local prompt checks. |
| **Qwen3.5 2B** | **Q4_K_M, approximately 1.3 GB** | **Selected MVP candidate** for local conversation and bounded intent routing. It is not approved for autonomous reasoning, code changes or trading decisions. |

The upstream Qwen3.5-2B model card states Apache-2.0 licensing and support for 201 languages/dialects. The tested GGUF artifact was obtained from `vultr/Qwen3.5-2B-GGUF`; verify provenance and license again before replacing the artifact. Upstream model card: https://huggingface.co/Qwen/Qwen3.5-2B

**Selected artifact:** `Qwen3.5-2B-Q4_K_M.gguf`
**SHA-256:** `cd1950c433492e0bbf2e64f32486c525af0e0bf2ab98dd73c329e597ef282f2d`
**Local path:** `/opt/hes-trade-agent/forward/hoshyar-runtime/models/Qwen3.5-2B-Q4_K_M.gguf`

## Runtime and resource policy

- CPU-only `llama.cpp` server, build release `b12248`.
- Bind only to `127.0.0.1:18082`; OpenAI-compatible chat-completions endpoint.
- 4,096-token context, one parallel slot, Qwen reasoning mode off for normal chat, two inference threads.
- `nice -n 10`; systemd candidate limits: CPUQuota 125%, CPUWeight 20, MemoryHigh 2.6 GiB, MemoryMax 3 GiB, OOMScoreAdjust 500.
- The proposed systemd unit denies non-local network access and requires an API-key file with mode 0600.
- No Ollama/CUDA stack is required. The thin dashboard does not embed the model.

Observed generation speed: approximately 3.7–3.8 tokens/s at one thread and approximately 7 tokens/s at two threads on the VPS. Prompt evaluation in the two-thread test was approximately 19 tokens/s. The Qwen2B server process showed roughly 2.1 GiB RSS; available memory remained around 4.1–4.4 GiB in the observed tests. These are point-in-time measurements, not a long-duration concurrency guarantee.

## Integration contract

1. `HoshyarLocalLLMV1` accepts only `http://127.0.0.1:18082/v1/chat/completions`; remote hosts, HTTPS endpoints, alternate ports and arbitrary paths are rejected.
2. If `/var/lib/hes-news-monitor/hoshyar-llm-api-keys` exists, the client reads its first non-comment key only when the file is mode 0600 and sends it as a Bearer token. The server unit uses the same file. Missing local runtime causes deterministic fallback; it never falls back to a paid or remote model.
3. The model may classify into a fixed allowlist: status, decision explanation, market review, journal review, news context, diagnostics, prepare-change, explain-change-control, project-memory lookup, unknown, or general chat. No model-generated tool/function calls are accepted.
4. For HES-specific requests, the existing Mother evidence readers execute the read-only lookup and produce the claims/evidence references. The model cannot invent or replace those facts. `PROJECT_MEMORY` is a separate read-only lexical search over only `docs/checkpoints`, `docs/architecture`, and `releases/deployment-records`; each match carries a SHA-256 reference. It does not access Notion-only pages, connected accounts, journals or secrets.
5. General chat is marked `CHAT_ONLY`, has no evidence claims, and returns explicit false values for `external_llm_used`, `execution_enabled`, `orders_placed`, `journal_write` and `policy_mutation`.
6. Conversation memory is local SQLite, one-owner, 30-day retention, maximum 200 stored messages; only the latest eight messages are passed as model context. The authenticated UI can retrieve the recent history and explicitly clear it. Filesystem reads use an explicit root allowlist, no-follow file opens, regular-file checks, bounded file sizes and bounded traversal.
7. The model has no trade, account, risk-policy, file-write, merge or deploy tools. Every production-affecting change remains behind the existing human approval gate.

## Memory location and control

Default database: `/var/lib/hes-news-monitor/hoshyar-memory.sqlite3`. The SQLite file is mode 0600. Retention is 30 days, with a 200-message cap. The model receives at most the last eight stored messages. The UI exposes a clear-memory action; clearing chat memory does not delete project DNA, checkpoints, journals or source files.

## Activation controls

- `HES_HOSHYAR_LOCAL_LLM_ENABLED` defaults to `0`; the existing deterministic Mother chat remains the default until explicitly enabled.
- `HES_HOSHYAR_LOCAL_LLM_MODEL=hoshyar-qwen35-2b-q4`.
- `HES_HOSHYAR_LOCAL_LLM_API_KEY_FILE=/var/lib/hes-news-monitor/hoshyar-llm-api-keys`.
- `HES_HOSHYAR_MEMORY_DB=/var/lib/hes-news-monitor/hoshyar-memory.sqlite3`.
- `deploy/systemd/hes-hoshyar-local-llm.service` is a proposed, validated unit; it has not been installed or enabled.
- `deploy/systemd/hes-readonly-dashboard-hoshyar.conf.example` is an activation drop-in template; it has not been installed.
- `deploy/scripts/prepare-hoshyar-local-api-key.sh` provisions a private local API key when activation is approved; it has not been run.

## Acceptance boundary

The candidate passed the isolated local staging test and the focused automated tests listed in the 2026-11-17 checkpoint. This proves the bounded conversation adapter and memory path work in staging. It does **not** mean the model is a fully capable autonomous LLM, that the service is enabled at boot, or that production dashboard code has been deployed. Production activation requires review/approval of the exact diff, service limits and rollout/rollback plan.
