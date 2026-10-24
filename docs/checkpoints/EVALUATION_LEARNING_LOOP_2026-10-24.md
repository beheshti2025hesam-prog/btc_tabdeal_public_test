# Evaluation & Learning Loop — 2026-10-24

## Decision
Reuse the existing Signal Agent, canonical native OHLCV source, and immutable forward observation writer. Do not create another signal, candle, execution, or frontend path.

## Implementation candidate
- PR: #367 (Draft, stacked on current Signal Agent PR #362): https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/367
- Decision journal integration: `web/dashboard.py` writes only when `HES_FORWARD_LEARNING_DECISION_JOURNAL` points to an explicitly configured durable path.
- Event identity pins source response hashes, strategy evidence hash, scope, observation time, and policy version. Repeated reads of identical evidence are idempotent; different outputs for the same evidence/policy fail closed.
- Decision records are immutable, forward-only and outcome-free. Existing `ForwardObservationWriterV1` is reused.
- Outcomes are a separate append-only artifact. `record_forward_outcome` requires a known LONG/SHORT decision, matching immutable decision digest, external evidence reference + SHA-256, and a timezone-aware causal close time. NO_TRADE cannot receive a trade outcome.
- `build_report_from_artifacts` verifies decision/outcome digests and lineage before passing joined rows to the existing `learning_loop_v1` attribution engine.
- CLI: `python -m scripts.run_forward_learning_report_v1 --decisions <decision.jsonl> --outcomes <outcomes.jsonl> [--output <report.json>]`
- Hypotheses remain research-only; no automatic threshold/strategy change.

## Required operational configuration
The dashboard does not create a journal file unless `HES_FORWARD_LEARNING_DECISION_JOURNAL` is explicitly set. Configure this only after an authorized runtime owner chooses and validates a durable writable location. The separate outcome file must be populated only from independently reconciled forward outcome evidence; this PR does not invent or infer outcomes.

## Safety and acceptance
- Execution OFF; no order route, live trade, service activation, deployment, or VPS mutation.
- Historical/Winner/Survivor populations remain excluded.
- Product remains HOLD / NO_TRADE_ONLY.
- PR #367 is Draft/unmerged. Do not accept the loop end-to-end until exact-head CI passes, the authorized durable path is configured, actual forward decisions accumulate, and separately reconciled closed outcomes are verified.
- Delivery target: 2026-11-19. Risk checkpoint: 2026-10-26. Exactly one VPS.
