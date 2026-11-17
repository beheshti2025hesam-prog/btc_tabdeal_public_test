# HES Trade AI — Local Model Benchmark & Integration Checkpoint

**Date:** 2026-11-17
**Status:** `STAGING_PASS / PRODUCTION_NOT_ENABLED`
**Branch:** `feat/hoshyar-local-ai-v1` (based on the deployed Mother chat release)
**Production dashboard:** unchanged; local-model feature flag defaults off. User-facing name is HES Trade AI; legacy HOSHYAR names remain internal identifiers only.

## Completed

- Read-only VPS capacity inspection: 2 vCPU, 5.8 GiB RAM, 2 GiB swap, approximately 22 GiB disk free before model downloads, no NVIDIA GPU.
- Compared Qwen3.5 0.8B, Gemma 3 1B IT and Qwen3.5 2B candidates. Selected Qwen3.5 2B Q4_K_M as the MVP conversational/intent-routing candidate; smaller candidates did not meet the Persian instruction/safety bar.
- Downloaded and SHA-256 verified the Qwen3.5 2B Q4_K_M GGUF artifact. The model is open-weight under the upstream Apache-2.0 license; upstream model card documents 201 languages/dialects.
- Benchmarked CPU-only llama.cpp b12248 on the VPS. Approximate generation: 3.7–3.8 tokens/s with one thread; approximately 7 tokens/s with two threads. Model process RSS was about 2.1 GiB. Available memory remained about 4.1–4.4 GiB during observed tests while HES services remained active.
- Implemented an optional local-only adapter in an isolated branch. It rejects non-loopback endpoints, uses JSON-only intent routing, has no tools, and never calls a remote/paid LLM.
- Connected the adapter to the existing Mother chat/evidence readers in isolated staging. HES status and decision explanations still come from the existing deterministic readers; the model only routes the natural-language request.
- Added a read-only project-memory reader for approved local Markdown checkpoints, architecture notes and deployment records. It returns bounded excerpts with SHA-256 evidence references; it does not query Notion-only pages or connected accounts.
- Retrieved the canonical 2026-11-17 HES Trade AI DNA from the connected Notion workspace and copied a dated, source-linked snapshot into `docs/checkpoints/HES_TRADE_AI_DNA_2026-11-17.md` for local read-only retrieval. This is a snapshot, not live Notion synchronization. Applied the approved user-facing names HES Trade Agent / HES Trade AI / HES Command Center and added `docs/architecture/HES_PRODUCT_NAMING_V1.md`; legacy HOSHYAR identifiers remain internal only.
- Hardened project-memory reads against symlink traversal/races, capped file traversal and file size, and prevented casual greetings from bypassing HES evidence routing when the message also mentions market/trading context.
- Added SQLite conversation memory: 30-day retention, 200-message cap, last eight messages supplied as context, authenticated history endpoint and explicit clear-memory endpoint.
- Added a deterministic change-control explanation intent. Production change requires approval of the exact diff and target, isolated tests, review and rollback plan.
- Added a resource-limited systemd unit template, a dashboard activation drop-in example and a private API-key provisioning script. None has been installed or enabled.

## Staging end-to-end evidence

A temporary staging dashboard was bound to `127.0.0.1:18766`; the local model server was bound to `127.0.0.1:18082`. A temporary test-only access token and temporary SQLite database were used and removed/cleared after the test.

| Test | Observed result |
|---|---|
| Local session login | HTTP 200 |
| Persian greeting | `GENERAL_CHAT`, `CHAT_ONLY`, local model used, memory used |
| HES status query | `ASK_STATUS`, existing Mother readers returned evidence-backed status |
| Follow-up decision question | `EXPLAIN_DECISION`, evidence refs returned by Mother readers |
| History endpoint | HTTP 200, six messages, local model enabled |
| Clear-memory endpoint | HTTP 200, status `CLEARED` |
| History after clear | HTTP 200, zero messages |
| External model use | `false` in every response |
| Execution / orders | `execution_enabled=false`, `orders_placed=false` |

The staging status snapshot reported Mother `BLOCKED_GATE`, Strategy V2 `VERIFIED`, News monitor `BLOCKED`, with `REQUIRED_CHECK_FAILED` on the Mother gate. This is the existing HES evidence observed during the test, not a HOSHYAR side effect. HOSHYAR did not change it.

## Automated tests

Command:

```bash
PYTHONPATH=/opt/hes-trade-agent/forward/hoshyar-integration-worktree \
  /opt/hes-trade-agent/.venv/bin/pytest -q \
  tests/test_hoshyar_local_v1.py \
  tests/test_hoshyar_dashboard_integration_v1.py \
  tests/test_hoshyar_project_memory_v1.py \
  tests/test_mother_chat_v1.py \
  tests/test_dashboard_routes_v1.py \
  tests/test_dashboard_localization_v1.py \
  tests/test_dashboard_orders_placed_contract_v1.py
```

Result after the HOSHYAR and project-memory hardening: **1,406 passed, 82 subtests passed in 19.00 seconds** across the full repository suite. The dashboard JavaScript passed `node --check`; all changed Python modules passed `py_compile`; the proposed systemd unit passed `systemd-analyze verify`; the API-key provisioning script passed `bash -n`. The systemd verifier also printed a pre-existing host warning for `/etc/systemd/system/xray.service` (`User=nobody`); it did not identify an error in the HOSHYAR unit.

## Important limits

- This 2B model is a small conversational/router model, not a replacement for specialist agents, not a reliable code-generation engine and not an autonomous trader.
- Persian/multilingual checks are a focused smoke test, not a comprehensive language-quality evaluation.
- Project-memory search is intentionally limited to local approved Markdown roots. Notion-only Master Checkpoint content is not automatically available through this reader and must be connected through an approved Notion read-only connector before it can be searched.
- Inference speed is modest on 2 vCPU; normal chat should stay concise and the UI must remain thin.
- No production systemd unit was installed, no production service was restarted, no release symlink was changed, and no production feature flag was enabled.
- Model artifacts are kept outside Git under `/opt/hes-trade-agent/forward/hoshyar-runtime`; they must not be committed to the repository.

## Remaining gate

Review the exact code diff and service resource/security policy. Only after explicit owner approval should the API-key provisioning script be run, the local LLM service be installed/enabled, the dashboard drop-in be installed, the new release be deployed and the feature flag enabled. Rollback is to remove the dashboard drop-in/disable the local service; the deterministic Mother chat remains the fallback.


## Local API authentication check

- An unauthenticated request to the model server returned HTTP **401**.
- The local adapter read a temporary API key from a mode-0600 file and completed Persian chat successfully with `external_llm_used=false`.
- The end-to-end staging dashboard test was repeated with the API-key-protected model server and passed login, Persian greeting, evidence-backed status, decision follow-up, history retrieval and memory clearing.
- Temporary API key, test access token, staging dashboard process, model server process and temporary SQLite databases were removed/stopped after the test. The selected model artifact remains stored locally; no model service is running or enabled.
