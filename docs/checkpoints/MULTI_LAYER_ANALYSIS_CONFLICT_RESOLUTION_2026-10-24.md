# HES Trade Agent — Multi-layer Analysis & Agent Disagreement Checkpoint

**Date:** 2026-10-24  
**Delivery target:** 2026-11-19  
**Risk checkpoint:** 2026-10-26  
**State:** `HOLD / NO_TRADE_ONLY`; live execution OFF.

## Existing canonical implementation — reuse, do not duplicate

Repository: `beheshti2025hesam-prog/btc_tabdeal_public_test`.
- Market data and candle/feature contract: PR #297, `NativeOHLCVBatch`.
- Existing dashboard and chart: PR #346, `web/dashboard.py`.
- Existing Signal Agent, strategy evidence provider, strategy quorum, confirmation engine/policy, risk gate/policy, decision engine, and order-block context: PR #362 (`feat/hes-agent-entrypoint-integration-20261024`).
- Execution preflight and journal: PR #363 (`feat/hes-live-execution-gates-20261024`).
- Keep PR #361 and #362 overlapping implementations reconciled before merge; never merge both copies of the same component.

## Verified multi-layer behavior

1. The strategy provider uses the same canonical Binance Spot BTCUSDT closed-candle source for 15m and 4h, pins raw response and eligible-window hashes, and blocks stale/gapped data or unestablished direction.
2. Strategy policy version `hes-strategy-policy-v1` requires 5 of 6 checks, with five non-negotiable checks: HTF trend alignment, pullback location, confirmed break, ADX/DI directional strength, and valid 3:1 geometry. MFI is the only optional vote. This is a conservative rule hypothesis, not a proven performance improvement.
3. Order-block scoring is explicitly `CONTEXT_ONLY`; it cannot overrule strategy quality, confirmation, risk, or final decision.
4. Confirmation requires a valid candidate plus contemporaneous direction/regime and structural-event checks. The risk policy rejects missing/UNKNOWN evidence and requires explicit risk context.
5. Final decision is LONG/SHORT only if candidate, confirmation, and risk all independently pass in the same direction. Otherwise `NO_TRADE`. Missing risk context currently remains UNKNOWN, so the present provider path should remain blocked.
6. The current implementation is deterministic/fail-closed; it does not yet establish a separate, explicit weighted consensus or explainable arbitration record across multiple independent specialist-agent outputs. Do not claim that a general multi-agent disagreement resolver is complete.

## Conflict-resolution contract required for acceptance

The existing independent gates remain authoritative; do not add another parallel decision engine. Any extension should be a small adapter/orchestrator over existing outputs and must:

- Compare exact scope: venue, product, symbol, timeframe, direction, and common closed-candle `as_of`/evidence hash.
- Reject mixed/stale/future scopes and contradictory LONG vs SHORT opinions; disagreement yields `NO_TRADE`, never majority-vote override of a mandatory gate.
- Distinguish `FAIL` from `UNKNOWN`; missing evidence never counts as agreement or a positive vote.
- Preserve per-agent version, state, reason codes, evidence refs/hashes, timestamp, and conflict classification in an auditable record.
- Apply precedence: data-quality veto → market/regime/structure validity → strategy mandatory gates → confirmation → risk veto → decision. Risk veto is absolute. Context-only OB scores and soft/optional evidence cannot override mandatory failures.
- Be deterministic and idempotent for identical input evidence. Do not silently average incompatible outputs or auto-tune thresholds.
- Add adversarial tests for opposing directions, stale/mismatched hashes, duplicate agent reports, UNKNOWN vs FAIL, mandatory-gate veto despite majority, malformed/future timestamps, and identical-input reproducibility.

## Current exact-head evidence (PR #362 head `69165f832285118d932779a95e4f849320be978f`)

- Signal Agent contract suite: PASS, 79 tests — workflow run `40081406221`.
- Signal Agent + existing-gate regression: PASS, 85 tests — workflow run `40081406242`.
- Dashboard/native path and browser render: PASS — runs `40081406265` and `40081406218`.
- Live WebSocket smoke: SKIPPED, not passed — run `40081406254`.

These prove software contracts and read-only UI behavior only; they do not prove profitability, runtime reachability, independent agent disagreement arbitration, or production readiness.

## Remaining acceptance blockers

- Implement and test the minimal auditable conflict-resolution adapter over existing agent outputs; avoid duplicate Signal/Confirmation/Risk/Decision modules.
- Wire the explicit adapter into the existing dashboard/API path and show the per-layer reasons and final veto source.
- Capture exact-SHA adversarial test evidence and browser/API integration evidence.
- Complete authorized runtime/source reachability, 24-hour data soak and separate reconnect/restart fault injection.
- Resolve PR dependency/overlap and independent review. Keep Draft/HOLD until then.
- Keep execution OFF until venue, account risk context, symbol mapping, exact deployment SHA, independent review, and operator approval are all proven.

## Anti-rework and schedule

Do not reimplement the existing indicator, market structure, OB, confirmation, risk, decision, dashboard, or candle-source components. New work must close the named arbitration gap with exact evidence and tests. Delivery remains **2026-11-19**; the **2026-10-26** risk checkpoint stays active until blockers have evidence-backed closure.
