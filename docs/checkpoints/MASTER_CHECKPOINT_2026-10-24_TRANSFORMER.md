# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Transformer Agent contract implemented; model promotion remains HOLD.** This branch adds a model-agnostic, fail-closed inference boundary and tests. It does not contain or claim a trained Transformer model, model weights, training pipeline, calibration evidence, or production performance proof.

## Reuse-first canonical path
Existing canonical data/feature pipeline → Transformer Agent evidence adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No second candle schema, indicator pipeline, dashboard, or collector is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: injected adapter contract for an existing trained model/runtime.
- `tests/test_transformer_agent_v1.py`: positive and negative contract tests.
- `forward/TRANSFORMER_AGENT_V1.md`: interface, non-goals, evaluation, and promotion criteria.
- `.github/workflows/transformer-agent-contract.yml`: dedicated CI contract workflow.
- Causal window validation: ordered timezone-aware timestamps, no future rows, freshness, row shape, finite numeric features, feature schema, model/source SHA-256, and model version.
- Output validation: LONG/SHORT/NEUTRAL probabilities must be finite, normalized, and schema-correct; neutral/low-confidence/malformed/runtime-failure cases abstain to UNKNOWN.
- Sequence lineage hash and machine-readable reason codes.

## Verification
CI run: [Transformer Agent Contract Tests](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40072072749), tested head `671656d6b55573d98e88772db9cec048c460c678`. At checkpoint creation, the workflow was still running; do not mark tests passed until its final conclusion is successful. Any code changes after this SHA require rerunning the workflow on the new head.

## Remaining gates before production use
1. Select an existing, maintainable model/runtime and create a separately reviewed adapter; verify model artifact hash and feature-schema compatibility.
2. Record training data lineage, labels/targets, splits, normalization/scaler, hyperparameters, and reproducible training manifest.
3. Prove no look-ahead, label leakage, overlapping-window leakage, or OOS contamination.
4. Evaluate against existing strategy and naive baselines on identical immutable snapshots; include fees/slippage, calibration, coverage/abstention, drawdown, turnover, and regime stability.
5. Store immutable OOS/walk-forward evidence and obtain independent promotion approval.
6. Wire evidence into the existing Signal Agent only behind its current quality and Risk Gate contracts; then run paper/shadow validation.
7. Live execution remains separately gated and OFF.

The 0.60 default is only an abstention threshold, not a claim of 60% win rate or calibrated probability. No model is promoted automatically.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed for this branch.
- This branch is based on the existing Signal Agent candidate and is a Draft/HOLD until CI and review evidence are complete.
