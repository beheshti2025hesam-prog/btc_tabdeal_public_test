# HES Trade Agent — Master Checkpoint: Live Execution Boundary
Date: 2026-10-24

## Status
**HOLD / NO_TRADE_ONLY.** The live-execution work now includes a fail-closed preflight contract and a durable SQLite idempotency/state journal with negative tests. No live venue adapter is implemented or enabled. This is intentional: verified evidence does not yet support safe live orders.

## Canonical path (do not recreate)
- PR #297: canonical NativeOHLCV source/data contract.
- PR #346: existing read-only dashboard/chart on that data path.
- PR #361: reusable Signal Agent v1.
- PR #362: dashboard → Signal Agent API/UI integration.
- PR #363: live-execution preflight and journal candidate, stacked on #362.
- Candidate branch: `feat/hes-live-execution-gates-20261024`.
- New components: `forward/execution_gate_v1.py`, `forward/execution_journal_v1.py`, `tests/test_execution_gate_v1.py`, `tests/test_execution_journal_v1.py`, and the dedicated GitHub Actions contract workflow.
- The gate is a preflight only. The journal is persistence only. Neither calls an exchange or places orders. Runtime defaults are disabled and kill-switch state is not clear.

## Implemented in this checkpoint
- Required versioned provenance fields: source hash, mapping, structure, strategy quality, risk policy/evidence, account reconciliation, and deployment SHA.
- Freshness/timezone validation, positive finite order geometry and quantity checks, LONG/SHORT stop-target ordering, configurable minimum reward:risk (default 3:1), production environment and explicit operator/live-mode/venue/health/kill-switch prerequisites.
- Deterministic client-order ID; durable unique client-order/decision reservations; payload-conflict rejection; persisted order state across process/instance restart.
- Strict journal state transitions. Ambiguous submissions enter `UNKNOWN`; they cannot be resubmitted until explicit reconciliation evidence is recorded.
- Fail-closed handling of missing, malformed, stale, future-dated, duplicated, or unknown prerequisites.

## Verification evidence
All three workflows passed on code head `86154ffe06303389e071b2cb0ee53579ea2f295e`:
- Execution gate + journal contract tests: [run 40071620072](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40071620072).
- Dashboard/native-path tests: [run 40071620040](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40071620040).
- Browser-render smoke: [run 40071620075](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40071620075).

The branch head subsequently received documentation-only updates; no code changed after tested code head `86154ffe06303389e071b2cb0ee53579ea2f295e`. The live WebSocket smoke was skipped because the PR remains Draft. These are contract/regression checks, not live venue or trading-performance evidence.

## Hard blockers before live trading
1. PR #297/#346/#362 acceptance and exact target-runtime/browser parity.
2. Approved data-source reachability and same-window freshness/provenance from the permitted runtime.
3. Reviewed analysis-symbol → policy-symbol → execution-venue instrument mapping.
4. Validated causal structure and versioned strategy-level quality provider.
5. Actual entry/stop/target/quantity and policy-bound risk evidence from the accepted signal path.
6. Choose one execution venue and verify official order API, instrument rules, account/position mode, and venue constraints.
7. Implement and review the concrete venue adapter, protective-stop lifecycle, partial-fill handling, and venue-specific restart-safe reconciliation connected to the journal.
8. Exact-SHA venue-adapter mocks, then read-only account reconciliation and paper/shadow observation.
9. Explicit owner approval to enable live mode after all gates pass.

Do not work around these blockers with guessed symbol mappings, invented strategy thresholds, placeholder credentials, or a parallel order path.

## Environment / deployment guardrails
- One VPS only. Do not refer to a second VPS.
- Do not alter the VPS, reset/clean its dirty working tree, deploy, start collectors, expose credentials, or place live orders as part of this code-only checkpoint.
- The project has not been deployed by this change.
- Keep PR #363 Draft/HOLD until exact-head CI and review evidence are available.

## Delivery management
- Product delivery target: **19 November 2026**.
- Risk checkpoint: **26 October 2026**.
- Priority through the risk checkpoint: unblock canonical source/runtime evidence and select/verify the execution venue; then finish the concrete adapter and paper/shadow validation without weakening the gates.
- Do not turn planning estimates or passing unit tests into a production-readiness claim.
