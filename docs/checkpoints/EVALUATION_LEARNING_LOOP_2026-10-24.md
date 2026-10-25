# Evaluation & Learning Loop — 2026-10-24

## Decision
Reuse the existing Signal Agent, canonical native OHLCV source, immutable forward observation writer, runtime validation, and outcome-artifact reader. Do not create another signal, candle, execution, outcome ledger, or frontend path.

## Implementation candidate
- PR: #367 (Draft, stacked on current Signal Agent PR #362): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/367
- Decision journal integration: `web/dashboard.py` writes only when `HES_FORWARD_LEARNING_DECISION_JOURNAL` points to an explicitly configured durable path.
- Event identity pins source response hashes, strategy evidence hash, scope, observation time, and policy version. Repeated reads of identical evidence are idempotent; different outputs for the same evidence/policy fail closed.
- Decision records are immutable, forward-only and outcome-free. Existing `ForwardObservationWriterV1` and `forward_runtime_validation_v1` are reused.
- Realized outcomes stay in the existing separate immutable JSON artifact directory and are consumed by `build_report_from_forward_evidence`. No second outcome schema/writer was introduced. The existing reader validates event linkage, chronology, forward-only population, artifact hashes, and reports an evidence manifest.
- CLI: `python -m scripts.run_forward_learning_report_v1 --journal <decision.jsonl> --outcomes-dir <outcomes-directory> [--output <report.json>]`
- Hypotheses remain research-only; no automatic threshold/strategy change.

## Verification
- Exact tested head: `3533177ecd217b887e831138bcf4ed0e2c0ecf36`.
- Evaluation and Learning Evidence Integration: [run 40095781507](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40095781507) — PASS.
- Forward Integration Verification v1: [run 40095781520](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40095781520) — test suite and execution/historical firewall steps passed; final cleanup was still in progress at checkpoint time.
- Dashboard/native path: [run 40095781471](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40095781471) — PASS.
- This is exact-head component/regression verification, not proof of live/production operation or realized performance.

## Required operational configuration
The dashboard does not create a journal file unless `HES_FORWARD_LEARNING_DECISION_JOURNAL` is explicitly set. Configure this only after an authorized runtime owner chooses and validates a durable writable location. The existing outcome directory must be populated only from independently reconciled forward outcome evidence; this PR does not invent or infer outcomes.

## Safety and acceptance
- Execution OFF; no order route, live trade, service activation, deployment, or VPS mutation.
- Historical/Winner/Survivor populations remain excluded.
- Product remains HOLD / NO_TRADE_ONLY.
- PR #367 is Draft/unmerged. Do not accept the loop end-to-end until exact-head CI passes on the final head, the authorized durable path is configured, actual forward decisions accumulate, and separately reconciled closed outcomes are verified.
- Delivery target: 2026-11-19. Risk checkpoint: 2026-10-26. Exactly one VPS.


## Follow-up — read-only journal projection candidate (2026-10-25)

- Branch: `feat/trade-journal-readonly-ui-20261025`.
- Reuses the existing decision journal configured by `HES_FORWARD_LEARNING_DECISION_JOURNAL`; no second journal or database is created.
- Adds `forward/trade_journal_view_v1.py`, a strict read-only projection that verifies each record digest and rejects malformed/partial, duplicate, tampered, non-forward, future/naive-timestamp, or outcome-contaminated records. UI output is bounded to 50 newest events and uses DOM `textContent` for untrusted values.
- Adds `GET /api/journal?limit=50` and a journal section in the existing `web/dashboard.py`. The panel explicitly labels decisions as learning evidence, not proof of executed trades; execution stays OFF and realized outcomes stay NOT_LINKED unless separately reconciled through the existing outcome-artifact contract.
- Adds adversarial tests for valid projection, tampering, partial trailing line, duplicate identity, naive/future timestamps, outcome leakage, and invalid limits. CI workflow now includes this test module.
- This is a new candidate diff, **not yet CI-verified or production deployed**. No VPS/runtime configuration was changed; journal remains unconfigured unless an operator explicitly supplies a durable path.
- Exact-head CI and test-log inspection are mandatory before acceptance. Keep PR #367 and its parent chain Draft/HOLD; do not merge this stack independently.
- Product delivery target remains **2026-11-19**; risk checkpoint remains **2026-10-26**. Status remains **HOLD / NO_TRADE_ONLY**.
