# HES Trade Agent — Master Checkpoint: Risk Gate & Product Connection

**Checkpoint date:** 2026-10-24  
**Delivery target:** 2026-11-19  
**Risk checkpoint:** 2026-10-26 until critical blockers clear  
**Status:** `HOLD / NO_TRADE_ONLY`; live execution remains OFF.

## Canonical path — do not duplicate

- Repository: `beheshti2025hesam-prog/btc_tabdeal_public_test`.
- Existing product entry point candidate: `web/dashboard.py` on PR #346; Signal Agent API/UI integration candidate: PR #362.
- Canonical native OHLCV/data foundation: PR #297. Reuse `NativeOHLCVBatch` and its feature pipeline; do not introduce another candle schema, parallel dashboard, or separate source/feature path.
- Execution preflight, typed venue-neutral adapter contract, and durable idempotency/reconciliation journal are being re-stacked in PR #366 (`feat/hes-live-execution-gates-rebased-20261024`) on the current PR #362 head. PR #363 is the original divergent candidate and must not be merged.
- Do not independently merge overlapping PR #361 and #362. Reconcile exact SHAs and dependency ancestry for #297 → #346 → #362 → #366 before acceptance. Keep all candidate PRs Draft/HOLD pending review and prerequisite acceptance.
- The project has one VPS only. Do not create or assume a second VPS.

## Verified evidence

- On VPS `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`; working tree is dirty. Preserve all uncommitted changes; do not reset, clean, or overwrite.
- Full VPS test suite on the current working tree: **398 passed**. Focused risk/firewall/market-data suite: **44 passed**.
- Gate.io public 15m/1h/4h data-only services were active when checked on 2026-10-24. The 24-hour read-only soak process is running but has **not** completed and is not a pass. Separate reconnect/restart fault-injection evidence is outstanding.
- Original PR #363 exact candidate head `9a88f959e5f5038211c968cf331c50c7a1a80e4a`: execution-gate/adapter/journal tests passed (29); dashboard/native-path and browser render workflows succeeded. Live WebSocket smoke was **skipped**, not passed. These are historical results, not proof for the re-stacked branch.
- Replacement PR #366 is based on exact PR #362 head `eccbfe19af37d8629070a2c1788d4c6a73824df1`. At checkpoint update, execution-gate tests and browser-render smoke are running, dashboard/native-path passed, and live WebSocket smoke was skipped. Exact-head CI is not yet complete.
- PR #362 candidate head `69165f832285118d932779a95e4f849320be978f`: Signal Agent contract/regression and dashboard/browser workflows succeeded; live WebSocket smoke was **skipped**, not passed.

## Risk and execution invariants

- Missing/unknown risk context, unverified source/venue mapping, stale/future evidence, invalid stop/target geometry, or failed mandatory gates must block approval.
- Signal output is not permission to submit an order. The execution gate requires pinned evidence, independent review, account reconciliation, venue health, kill-switch clearance, explicit operator approval, exact deployment SHA, and production runtime state.
- No venue has been approved for leveraged/live execution. No concrete venue-specific execution adapter is accepted. Do not infer order, protective-order, idempotency, position-mode, or reconciliation semantics from another exchange.
- No deployment, collector activation, credentials/private account access, or live order is authorized by this checkpoint.

## Multi-layer analysis and agent disagreement — 2026-10-24

- Existing implementation is in PR #362: `StrategyEvidenceProviderV1`, `StrategyPolicyV1`, `ConfirmationEngineV1`/`ConfirmationPolicyV1`, `RiskGateV1`/`RiskPolicyV1`, `DecisionEngineV1`, and contextual-only order-block scoring. Reuse these; no parallel engine.
- Strategy policy `hes-strategy-policy-v1` requires 5/6 checks, but only MFI is optional; HTF alignment, pullback location, confirmed break, ADX/DI directional strength, and valid 3:1 geometry are mandatory. This is a conservative hypothesis, not a measured win-rate improvement.
- The current final resolver returns LONG/SHORT only when candidate, confirmation, and risk independently pass; otherwise NO_TRADE. Unknown risk context is currently emitted by the evidence provider, so this path remains blocked. Order-block score cannot overrule mandatory gates.
- Exact PR #362 head `69165f832285118d932779a95e4f849320be978f`: Signal Agent contract 79 passed; existing-gate regression 85 passed; dashboard/native and browser render workflows passed. Live WebSocket smoke was **SKIPPED**, not passed.
- The separate auditable disagreement resolver is implemented on PR #362: `forward/agent_disagreement_resolver_v1.py`, adversarial tests, and read-only `/api/signal` wiring. Exact-head Signal Agent contract/regression, dashboard/native path, and browser-render CI passed. Live WebSocket smoke remains skipped. Runtime reachability and end-to-end operational behavior are not thereby proven.
- Resolver contract now enforces exact common scope/as-of/snapshot hash; opposing LONG/SHORT, stale/future/mismatched evidence, duplicate or missing reports, and UNKNOWN fail closed to NO_TRADE; risk veto is absolute; contextual scores cannot override mandatory failures. Remaining acceptance is final stack review plus operational/source/runtime evidence.

## Multi-layer analysis and disagreement resolver implementation — 2026-10-24

- Added `forward/agent_disagreement_resolver_v1.py` on PR #362 branch `feat/hes-agent-entrypoint-integration-20261024`, commit `de85274cc62d3251abee2f49feb668083b4e5061`. It is a thin deterministic adapter over existing layer outputs; it does not duplicate indicators or policies.
- Added adversarial tests at `tests/forward/test_agent_disagreement_resolver_v1.py`, commit `0bbb49990ef708910df1c5138f864b9028b08336`: opposing LONG/SHORT, mismatched source snapshot hash, as-of mismatch, symbol mismatch, risk veto despite majority, UNKNOWN evidence, duplicate reports, future timestamps, missing required agent, naive timestamp, and deterministic replay.
- Wired the existing read-only `GET /api/signal` in `web/dashboard.py` to create a common two-timeframe snapshot fingerprint, adapt data-quality/structure/strategy/confirmation/risk outputs, and expose the complete arbitration audit record. Commits `592e41375b8ab32dc32d670b5836f4fff92297d6` and follow-up safety fix `67f6c511e4b7bb92e8c95006faaa3c7bd29ad9eb`.
- Updated both existing Signal Agent CI workflows to run the new adversarial suite: `85a93c478294a966aa9a676642f1357598fba714` and `eccbfe19af37d8629070a2c1788d4c6a73824df1`.
- Exact-head CI for PR #362 head `eccbfe19af37d8629070a2c1788d4c6a73824df1`: Signal Agent Contract Tests **PASS** (run `40092480444`, includes the new resolver test file); dashboard/native-path **PASS** (run `40092480416`); Signal Agent + existing-gate regression **PASS** (run `40092480399`); browser render with same-batch chart/API comparison **PASS** (run `40092480306`). Live WebSocket smoke is **SKIPPED**, not passed, because the PR remains Draft.
- Integration remains fail-closed: data quality must pass, all required agents must report the same venue/product/symbol/timeframe, identical closed-candle as-of and common snapshot hash, no UNKNOWN/FAIL, and no opposing directional opinions. Risk rejection is an absolute veto. If the dashboard has any blocked reason, final API decision remains NO_TRADE.
- Important dependency condition: PR #363 is stacked on an earlier PR #362 head. The new resolver commits are currently on PR #362 branch; reconcile/rebase the stack and rerun exact-head CI before treating PR #363 or the whole product chain as merge-ready.

## Blocking acceptance gates

1. Approve one supported execution venue only after authoritative official documentation and independent review of order types, quantity units/filters, protective orders, client-order idempotency, timeout-after-accept handling, positions, and account reconciliation.
2. Resolve authorized runtime reachability for the chosen market-data source and prove exact-head same-batch source → features → Signal Agent → Risk Gate → dashboard output. A GitHub runner result does not prove VPS reachability.
3. Complete and review the 24-hour feed soak; separately test forced disconnect/reconnect and service restart, including stale/gap rejection and duplicate handling.
4. Resolver implementation and adversarial tests are present on PR #362 and exact-head CI passed. Keep this gate open only for final stack review and proof that the same behavior holds in the authorized target runtime; do not claim runtime acceptance from GitHub CI alone.
5. Reconcile PR dependency chain and exact SHAs; obtain required review and CI on the final candidate. Do not merge competing implementations independently.
6. Confirm the actual authorized application/runtime deployment entrypoint and capture target-runtime browser/chart parity before claiming product connection complete.
7. Keep live execution OFF until all independent evidence and operator approval gates pass.

## Anti-rework rule

Memory/checkpoints are the project map; GitHub is technical source of truth; chat is the working log. Reuse existing modules and the canonical `NativeOHLCVBatch` path. Any new work must close a named acceptance blocker with exact-SHA evidence and regression tests; do not recreate existing components or invent missing provider behavior.

## Delivery management

Target remains **2026-11-19**. The **2026-10-26** risk checkpoint remains active until source reachability, target-runtime product wiring, soak/fault-injection, venue qualification, and independent review have evidence-backed closure. Resolver code/test coverage is implemented, but does not remove those operational gates. Do not claim the risk/product/analysis sections fully complete before these gates pass.
