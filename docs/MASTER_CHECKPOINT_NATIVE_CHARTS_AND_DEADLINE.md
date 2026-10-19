# HES Trade Agent — Master Checkpoint & Non-Negotiable Guardrails

**Checkpoint recorded:** 2026-10-19  
**Project delivery deadline:** **28 Aban 1405 (1405/08/28 — 2026-11-19)**

## Core architecture decision — DO NOT REOPEN WITHOUT EVIDENCE

- **Use the charts and candlesticks already provided by exchange/broker applications and their supported native data interfaces.**
- **Do not build a candle-generation system or recreate OHLCV as a project objective.** This is a settled decision, not an open design question.
- First inspect and reuse existing platform capabilities and existing HES code. Make only the smallest change needed to connect, validate, and analyze existing native data.
- Do not resume an OHLCV/candle adapter effort (including treating PR #327 as strategic direction) unless a specific, evidenced requirement proves native platform access is insufficient. Document that evidence and rationale before implementation.
- Avoid duplicated work: inspect the repository, existing PRs, tests, and completed CI evidence before changing code or rerunning checks. Rerun completed checks only after relevant code changes or new evidence.
- Do not claim a gate has passed without verifiable evidence tied to the exact commit and artifacts.

## Safety state

**HOLD / NO_TRADE_ONLY.** No live trading activation, no merge, and no source/evidence-gate acceptance without the required verified evidence and all applicable gates passing.

## Working protocol

1. Treat GitHub as the technical source of truth; conversation is the working notebook; memory is a navigation aid.
2. Before implementation, identify the existing native chart/candle access path and the smallest missing integration/validation capability.
3. Report to the user in concise, plain Persian; prioritize execution and minimize confirmation requests.
4. Keep the delivery deadline visible in every master checkpoint/release plan: **28 Aban 1405 / 19 November 2026**.

## Anti-duplication reminder

**Reuse existing native charts/candles. Do not rebuild the wheel. Optimize the integration, evidence, validation, and analysis layers only where a demonstrated gap exists.**
