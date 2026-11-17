# HES Persian Evaluation v3 — Artifact Guide

This bundle contains the standard executed Jupyter notebook, versioned Persian regression suite, actual Qwen3.5-2B one-off result, deterministic eight-turn results, comparative report, validation records, and reproducible runners.

## Important distinctions

- The Qwen3.5-2B result is a real one-off local inference run, but its evidence fixtures are synthetic. It scored 6/8 functional turns and is NO-GO for production.
- The deterministic eight-turn re-run is a real execution of the candidate Mother/Hoshyar code with synthetic evidence fixtures and a dummy model that raises if called. It scored 8/8 with zero local-LLM calls.
- The focused candidate test suite passed 53 tests, including 14 Persian-specific tests.
- No production release or service was changed. The persistent local model service remains disabled.

## Reproduce

From the repository root:

- `python research/llm_eval_2026-11-17/run_persian_eval_v2.py`
- `python research/llm_eval_2026-11-17/run_persian_eight_turn_v2.py`

Only on the HES VPS, and only while the persistent Hoshyar model service remains disabled:

- `python research/llm_eval_2026-11-17/run_qwen35_2b_eval.py`

The Qwen runner refuses to run if the persistent service is active/enabled or port 18082 is occupied. It starts a temporary low-priority loopback-only process, uses no API key or remote fallback, and terminates it after the run. It requires the exact model and llama.cpp artifacts already present on the VPS; model binaries are not included in this bundle.

## Files

- `HES_Persian_Mother_Chat_Evaluation_v2.ipynb` — executed nbformat-4 notebook with saved outputs.
- `persian_test_suite_v2.json` — versioned Persian scenario contract.
- `DETERMINISTIC_MOTHER_CHAT_RESULTS_v2.json` — eight scenario results.
- `PERSIAN_8_TURN_DETERMINISTIC_RESULTS_v2.json` — eight-turn conversational result.
- `QWEN35_2B_PERSIAN_8_TURN_RESULTS.json` — local model run, raw responses and metrics.
- `LOCAL_MODEL_COMPARISON_HISTORY.json` and `COMPARATIVE_REPORT_v2.md` — model comparison and decision.
- `MAINLINE_EXACT_HEAD_VALIDATION.json` and `CANDIDATE_PATCH_VALIDATION.json` — test evidence and source hashes.
- `run_persian_eval_v2.py`, `run_persian_eight_turn_v2.py`, `run_qwen35_2b_eval.py` — reproduction scripts.
- `FINAL_MANIFEST_v2.json` — SHA-256 manifest.
