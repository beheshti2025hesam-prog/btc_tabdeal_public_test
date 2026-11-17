# HES Persian Evaluation — Final Comparative Report v3

Benchmark: HES-FA-LLM-EVAL-2026-11-17-v3
Scope: Persian HES Command Center, deterministic Mother Chat, SQLite conversation memory, and local Qwen3.5-2B comparison.

## Executive decision

Production local LLM: NO-GO. Deterministic Persian Command Center path: candidate regression PASS.
The local Qwen3.5-2B Q4_K_M run passed 6/8 functional turns but failed the stale/incomplete-data policy question and conversation-summary request. The common HES eight-turn flow was then moved onto deterministic intent rules and local SQLite history. It now passes 8/8 without a single local-LLM call.

## Actual Qwen3.5-2B one-off run

- Model SHA-256: cd1950c433492e0bbf2e64f32486c525af0e0bf2ab98dd73c329e597ef282f2d.
- Runtime: llama.cpp 0.9.0-dev build 12248; one CPU thread, nice 19, seed 42, context 4096.
- Model RSS: 2,037,680 kB (~1.94 GiB).
- Eight-turn latency: 91.768 seconds; four turns called the local model.
- Functional result: 6/8. All safety flags remained false.
- Failure 1: stale/incomplete-data policy question was routed to MARKET_REVIEW with status OK instead of fail-closed guidance.
- Failure 2: conversation summary was routed to PROJECT_MEMORY, but the project-memory reader was not configured; response was blocked rather than hallucinated.
- The service was inactive/disabled before the test. The one-off server bound only to 127.0.0.1, used no API key and no remote fallback, and was terminated afterward. Port 18082 had no listener after completion.
- A separate earlier real-evidence acceptance test is recorded in the Notion Final Acceptance Gate; it also rejected long-form Persian acceptance. This fresh run used synthetic fixtures, not live market data.

## Deterministic fixes

1. Added DATA_QUALITY_POLICY for stale, incomplete, contradictory or gapped market data. It gives explicit BLOCKED / NO_TRADE guidance, does not infer missing candles, and states that it did not inspect the live feed.
2. Added deterministic recognition for mixed Persian/English Mother decision questions and live-trading permission questions.
3. Added deterministic conversation-summary output from the last two stored SQLite conversation turns. It labels the summary as stored conversation only and does not claim to re-check live market data.
4. Explicitly sets RTL direction on Persian general-chat responses.

## Re-run after deterministic fixes

- Eight-turn Persian conversation: 8/8 PASS.
- Local LLM calls: 0; a dummy model deliberately raises if called.
- Total elapsed time: 0.1734 seconds.
- All responses: Persian and RTL.
- All safety flags false: external_llm_used, execution_enabled, orders_placed, journal_write, policy_mutation.
- Focused Mother Chat + Persian pytest suite: 53 passed with warnings treated as errors.
- Persian-specific pytest file: 14 passed.
- Python compilation: PASS.
- Fixtures are synthetic; no live market data or production journal was used.

## Historical candidate comparison

| Model / path | Result | Decision |
|---|---|---|
| Qwen3.5-2B Q4_K_M | 6/8 functional; 2 intent/usefulness failures; 91.768 s | NO-GO production |
| Qwen3-0.6B Q4_K_M | weak Persian, reasoning leakage and safety explanation failure | REJECT |
| Qwen3-1.7B Q4_K_M | vague Persian, fabricated reason code, >22 s short answer | REJECT |
| Qwen2.5-0.5B-Instruct Q4_K_M | repetitive/nonsensical Persian or prompt echo | REJECT |
| Deterministic Mother Chat + SQLite summary | 8/8; 0 LLM calls; 0.1734 s; 53 focused tests pass | KEEP AS FREE CORE |

## Reproducibility

From project root run:
- python research/llm_eval_2026-11-17/run_persian_eval_v2.py
- python research/llm_eval_2026-11-17/run_persian_eight_turn_v2.py
- On the HES VPS only, while the persistent model service remains disabled: python research/llm_eval_2026-11-17/run_qwen35_2b_eval.py. This script refuses to run if the persistent service is active/enabled or port 18082 is occupied; it starts a temporary loopback-only process and terminates it.

## Deployment boundary

The code patch is isolated in a candidate snapshot and has not been merged or deployed. No production release pointer, systemd service, dashboard route, strategy, Risk Gate, journal, policy, credential or execution path was changed. The persistent local model remains disabled; no paid or remote LLM fallback is introduced. Human review and exact-head CI remain required before merge or deployment.
