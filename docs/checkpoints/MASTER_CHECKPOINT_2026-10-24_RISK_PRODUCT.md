# HES Trade Agent — Master Checkpoint: Risk Gate & Product Connection

**Checkpoint date:** 2026-10-24  
**Delivery target:** 2026-11-19  
**Risk checkpoint:** 2026-10-26 until critical blockers clear  
**Status:** `HOLD / NO_TRADE_ONLY`; live execution remains OFF.

## Canonical path — do not duplicate

- Repository: `beheshti2025hesam-prog/btc_tabdeal_public_test`.
- Existing product entry point candidate: `web/dashboard.py` on PR #346; Signal Agent API/UI integration candidate: PR #362.
- Canonical native OHLCV/data foundation: PR #297. Reuse `NativeOHLCVBatch` and its feature pipeline; do not introduce another candle schema, parallel dashboard, or separate source/feature path.
- Execution preflight, typed venue-neutral adapter contract, and durable idempotency/reconciliation journal: PR #363 (`feat/hes-live-execution-gates-20261024`).
- Do not independently merge overlapping PR #361 and #362. Reconcile exact SHAs and dependency ancestry for #297 → #346 → #362 → #363 before acceptance. Keep candidate PRs Draft/HOLD pending review and prerequisite acceptance.
- The project has one VPS only. Do not create or assume a second VPS.

## Verified evidence

- On VPS `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`; working tree is dirty. Preserve all uncommitted changes; do not reset, clean, or overwrite.
- Full VPS test suite on the current working tree: **398 passed**. Focused risk/firewall/market-data suite: **44 passed**.
- Gate.io public 15m/1h/4h data-only services were active when checked on 2026-10-24. The 24-hour read-only soak process is running but has **not** completed and is not a pass. Separate reconnect/restart fault-injection evidence is outstanding.
- GitHub PR #363 exact candidate head `9a88f959e5f5038211c968cf331c50c7a1a80e4a`: execution-gate/adapter/journal tests passed (29); dashboard/native-path and browser render workflows succeeded. Live WebSocket smoke was **skipped**, not passed.
- PR #362 candidate head `69165f832285118d932779a95e4f849320be978f`: Signal Agent contract/regression and dashboard/browser workflows succeeded; live WebSocket smoke was **skipped**, not passed.

## Risk and execution invariants

- Missing/unknown risk context, unverified source/venue mapping, stale/future evidence, invalid stop/target geometry, or failed mandatory gates must block approval.
- Signal output is not permission to submit an order. The execution gate requires pinned evidence, independent review, account reconciliation, venue health, kill-switch clearance, explicit operator approval, exact deployment SHA, and production runtime state.
- No venue has been approved for leveraged/live execution. No concrete venue-specific execution adapter is accepted. Do not infer order, protective-order, idempotency, position-mode, or reconciliation semantics from another exchange.
- No deployment, collector activation, credentials/private account access, or live order is authorized by this checkpoint.

## Blocking acceptance gates

1. Approve one supported execution venue only after authoritative official documentation and independent review of order types, quantity units/filters, protective orders, client-order idempotency, timeout-after-accept handling, positions, and account reconciliation.
2. Resolve authorized runtime reachability for the chosen market-data source and prove exact-head same-batch source → features → Signal Agent → Risk Gate → dashboard output. A GitHub runner result does not prove VPS reachability.
3. Complete and review the 24-hour feed soak; separately test forced disconnect/reconnect and service restart, including stale/gap rejection and duplicate handling.
4. Reconcile PR dependency chain and exact SHAs; obtain required review and CI on the final candidate. Do not merge competing implementations independently.
5. Confirm the actual authorized application/runtime deployment entrypoint and capture target-runtime browser/chart parity before claiming product connection complete.
6. Keep live execution OFF until all independent evidence and operator approval gates pass.

## Anti-rework rule

Memory/checkpoints are the project map; GitHub is technical source of truth; chat is the working log. Reuse existing modules and the canonical `NativeOHLCVBatch` path. Any new work must close a named acceptance blocker with exact-SHA evidence and regression tests; do not recreate existing components or invent missing provider behavior.

## Delivery management

Target remains **2026-11-19**. The **2026-10-26** risk checkpoint remains active until source reachability, product wiring, soak/fault-injection, venue qualification, and independent review blockers have evidence-backed closure. Do not claim the risk/product section fully complete before these gates pass.
