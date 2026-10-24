# HES Trade Agent — Master Checkpoint: Live Execution Boundary
Date: 2026-10-24

## Status
**HOLD / NO_TRADE_ONLY.** The live-execution section has a versioned fail-closed preflight contract and negative tests in a draft branch. No live venue adapter is implemented or enabled. This is intentional: the verified project evidence does not yet support safe live orders.

## Canonical path (do not recreate)
- PR #297: canonical NativeOHLCV source/data contract.
- PR #346: existing read-only dashboard/chart on that data path.
- PR #361: reusable Signal Agent v1.
- PR #362: dashboard → Signal Agent API/UI integration.
- PR #363: live-execution preflight candidate, stacked on #362.
- Candidate branch: `feat/hes-live-execution-gates-20261024`. It adds `forward/execution_gate_v1.py`, `tests/test_execution_gate_v1.py`, a dedicated GitHub Actions contract workflow, and this execution boundary documentation.
- The gate is a preflight only. It cannot place orders. Runtime defaults are disabled and kill-switch state is not clear.

## Implemented in this checkpoint
- Required versioned provenance fields: source hash, mapping, structure, strategy quality, risk policy/evidence, account reconciliation, and deployment SHA.
- Freshness/timezone validation, positive finite order geometry and quantity checks, LONG/SHORT stop-target ordering, configurable minimum reward:risk (default 3:1), production environment and explicit operator/live-mode/venue/health/kill-switch prerequisites.
- Duplicate-order preflight rejection and deterministic client order ID for a future durable journal.
- Fail-closed handling of missing, malformed, stale, future-dated, or unknown prerequisites.
- Contract tests for success-path preflight, default deny, missing provenance/account reconciliation, stale/future evidence, duplicate IDs, Long/Short geometry and RR, and proof the gate itself does not submit orders.

## Verification evidence
- Execution Gate Contract Tests passed on code head `f40e640f9b78a0d3625d94748651d6efa5dbc476`: [run 40071427149](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40071427149).
- The dashboard/native-path and browser-render smoke workflows were still running when this checkpoint was last updated; inspect their exact-head results before treating those checks as complete.
- A passing preflight contract test is not a live-trading proof. The interface is not a venue adapter.

## Hard blockers before live trading
1. PR #297/#346/#362 acceptance and exact target-runtime/browser parity.
2. Approved data-source reachability and same-window freshness/provenance from the permitted runtime.
3. Reviewed analysis-symbol → policy-symbol → execution-venue instrument mapping.
4. Validated causal structure and versioned strategy-level quality provider.
5. Actual entry/stop/target/quantity and policy-bound risk evidence from the accepted signal path.
6. Choose one execution venue and verify official order API, instrument rules, account/position mode, and venue constraints.
7. Build/review the concrete venue adapter, durable order journal, restart-safe reconciliation, protective stop acknowledgement, and ambiguous-submit recovery.
8. Exact-SHA mocked contract/regression tests, then read-only account reconciliation and paper/shadow observation.
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
- Priority through the risk checkpoint: unblock canonical source/runtime evidence and decide the execution venue; then finish the concrete adapter and paper/shadow validation without weakening the gates.
- Do not turn planning estimates or passing unit tests into a production-readiness claim.
