# HES Trade Agent — Productization & Public Distribution Roadmap Addendum

**Date:** 2026-10-01  
**Project:** HES Trade Agent  
**Owner:** Seyed Hesameddin Beheshti Shirazi

## Purpose

Preserve the future productization decision so it is not lost while current research and evidence work continues.

This is a **future roadmap item**, not a change to the current research gates, live-execution status, or project DNA safety boundaries.

## Future Public Product Direction

HES Trade Agent may later be productized as a public application and distributed through:

- **Google Play / Android**
- **Apple App Store / iOS**
- A web/API surface where useful

The mobile product should consume the HES core through a clean application/API boundary rather than coupling the mobile UI directly to the research/data-engine internals.

## Planned Product Architecture

HES Trade Agent Core
→ Research / Intelligence / Evidence services
→ Safe API / application boundary
→ Android UI + iOS UI + Web UI

Productization layers remain separate from:

- Raw Data / Collector integrity
- Evidence and OOS evaluation
- Candidate research gates
- Mother Brain safety boundary
- Live execution controls
- Wallet operations
- Secrets / credential layer

## Future Monetization Options

Subject to platform rules, legal/compliance review, and product validation:

1. Free tier with advertising
2. Premium / ad-free tier
3. Subscription or other permitted in-app purchase models
4. Developer/API access tier

For advertising, the app may later integrate an approved mobile advertising platform such as Google AdMob on Android and an appropriate Apple-compatible advertising/monetization mechanism on iOS.

**Important:** advertising must never influence market data, evidence, candidate evaluation, signals, risk controls, or Mother Brain decisions.

## Product Positioning / Safety

The public product should be positioned as a market-research, intelligence, analytics, and decision-support application unless and until a separately validated product scope permits anything broader.

No claims of guaranteed profit or guaranteed trading performance.

Live execution remains OFF until the existing promotion, safety, paper, and production gates are independently satisfied.

## Sequencing

This item is intentionally **future-facing**.

Current execution priority remains:

Evidence Gate Closure
→ formal checkpoint
→ independent Candidate B
→ fresh snapshot / walk-forward evaluation
→ cost / turnover gate
→ subsequent research and safety gates
→ later paper / production readiness
→ **then productization and public distribution planning**

This addendum must not be used as justification to skip or weaken any research, evidence, safety, or execution boundary.

## DNA Compatibility

This roadmap item follows the existing HES DNA principles:

- universal and transferable core
- modular / configurable / extensible architecture
- free-first where practical
- paid adapters/interfaces optional, not default
- analysis/research separated from live execution
- Mother Orchestrator is a command center, not an execution authority
- secrets remain in the secret layer
- Tabdeal BTC_USDT remains a first implementation, not the permanent product boundary

## Non-Regression Rule

Adding public distribution or monetization must never require:

- merging/rebasing/syncing `data-engine-v1` with `main`
- weakening Collector persistence or concurrency guarantees
- bypassing Evidence/OOS gates
- enabling live execution by default
- mixing advertising logic with trading/research decision logic
- changing the established progress-percentage methodology

## Acceptance

This document is the persistent roadmap memory for future Android/iOS/public-release work. It does not authorize implementation or publication now.
