# HES Trade Agent — Master Checkpoint: Live Trading

Checkpoint: 2026-10-24
Delivery target: 2026-11-19
Risk checkpoint: 2026-10-26
Status: HOLD / NO_TRADE_ONLY. Live execution OFF.

## Canonical implementation — reuse, do not duplicate
- Canonical market data and feature path: PR #297 / NativeOHLCVBatch.
- Existing dashboard/chart candidate: PR #346.
- Signal Agent and deterministic multi-agent disagreement resolver + read-only GET /api/signal: PR #362, exact head eccbfe19af37d8629070a2c1788d4c6a73824df1.
- Generic execution gate, typed venue-neutral adapter contract, durable idempotency/state journal, and adversarial tests: PR #366, branch feat/hes-live-execution-gates-rebased-20261024.
- Divergent predecessor PR #363 was closed unmerged. Do not recreate these components or merge PRs out of dependency order.

## Exact evidence
At tested code/test head 6e02f3c044acdeb60593dc84162cce7d68818881:
- Execution gate, journal, adapter contract: 32 tests PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40093527676
- Dashboard/native path: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40093527614
- Browser render and same-batch chart/API comparison: PASS — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40093527598
- Live WebSocket smoke: SKIPPED, not passed — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40093527642
- Current PR #366 metadata/documentation head is a639a9af0c7f6de15987da31846f888fdb34ef92; no execution code changed after the tested code/test head.

The generic contract is not a live implementation: there is no selected/approved venue and no concrete adapter wired to submit orders.

## Latest single-VPS read-only inspection
- Only VPS: /opt/hes-trade-agent, branch feat/gateio-global-market-data-v1, HEAD b2466bc118217dcc6446498effe38181589ed2db.
- Working tree has substantial pre-existing modified/deleted/untracked files. Preserve all; do not reset, clean, overwrite, or deploy the candidate branch over it.
- web/dashboard.py was absent from the current VPS tree at last detailed inspection; the target product entrypoint remains unproven on the VPS.
- Gate.io public market-data and forward Tabdeal collector services were active at the last check. Legacy hes-trade-agent-collector.service was failed.
- A read-only local health probe to 127.0.0.1:8000/health returned HTTP 000 / connection refused. This proves nothing is listening on that port; it does not prove which port (if any) is the authorized product runtime.
- No files or services were changed, restarted, or deployed. No account credentials were used and no order was placed.

## Required closure gates before live trading
1. Resolve final dependency ancestry and obtain independent reviews/required CI for PR #297 → #346 → #362 → #366; keep all Draft/HOLD until approved.
2. Identify and verify the actual product entrypoint and permitted runtime; prove end-to-end source → closed candles → features → multi-agent resolver → Risk Gate → UI/API on the exact candidate SHA.
3. Complete the 24-hour read-only feed soak and separate forced disconnect/reconnect, restart, stale/gap, and duplicate fault tests.
4. Select one legally/operationally supported venue based on official API evidence. Independently pin order semantics, client-order idempotency, instrument/symbol mapping, quantity units/precision/notional, account/position mode, cancellation, native protective stops, partial fills, and reconciliation.
5. Implement one concrete adapter against the existing typed interface; do not add a parallel order path. Validate timeout-after-accept, unknown outcome, partial-fill, cancellation/protective-order failure, restart recovery, and reconciliation with deterministic venue mocks.
6. Prove read-only balances/open orders/positions reconcile before and after paper/shadow execution. Complete paper/shadow soak and risk/operator review.
7. Live enablement requires separately authorized operator approval, pinned evidence/review revision, exact deployment SHA, explicit kill-switch state, and all gate outputs passing. Any unknown or mismatch => NO_TRADE.

## Safety and schedule
- Never place live orders, enable live mode, mutate the VPS, or restart production services as a substitute for missing evidence.
- No claim of live readiness or profitability from unit tests/CI alone.
- Target delivery remains 2026-11-19. The 2026-10-26 risk checkpoint is still active; schedule-critical blockers are runtime/product reachability, venue qualification, soak/fault evidence, and independent review.
- Master checkpoint must be updated after each material evidence-backed change. Memory is the project map; GitHub is technical truth; preserve existing implementations.
