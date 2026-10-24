# Transformer Agent v1 — Contract and Promotion Boundary

Status: **adapter-neutral inference boundary implemented; no trained model is promoted or enabled**.

## Reuse rule
The Transformer Agent sits behind the existing feature and evidence contracts. It does not replace the canonical OHLCV source, feature pipeline, Signal Agent, Risk Gate, Mother Orchestrator, or execution boundary. No second candle schema, indicator set, data collector, or order route is introduced.

## Responsibilities
- Accept a fixed ordered feature window and explicit feature names/schema version.
- Require a model version and SHA-256, source SHA-256, and observation timestamp.
- Reject missing or malformed metadata, short windows, mismatched row widths, nonnumeric/nonfinite values, duplicate/nonmonotonic timestamps, stale windows, and any timestamp later than the observation (look-ahead).
- Invoke an injected adapter for an existing trained model/runtime; validate exactly three normalized probabilities: LONG, SHORT, NEUTRAL.
- Return either EVIDENCE_ONLY or ABSTAIN/UNKNOWN with machine-readable reason codes and sequence lineage hash.
- Never create a trade order, bypass Signal Agent, or authorize execution.

## What is intentionally not invented
No Transformer architecture, training corpus, label policy, scaler, hyperparameters, model weights, probability calibration, or performance threshold is fabricated. The 0.60 default is only a conservative abstention/routing threshold, not a claim of 60% win probability. A production model requires a separately reviewed artifact, training-data lineage, calibration evidence, and out-of-sample/walk-forward evaluation.

## Evaluation / promotion sequence
1. Bind the adapter to a real, versioned model artifact and runtime; verify its hash and feature-schema compatibility.
2. Freeze train/validation/OOS boundaries and label/target definition; prove no future data or overlapping-label leakage.
3. Compare against the existing non-Transformer baseline and a simple naive baseline on identical immutable snapshots.
4. Report net-of-fee/slippage performance, calibration, coverage/abstention, drawdown, turnover, and stability across regimes; include confidence intervals where sample size permits.
5. Run adversarial tests for missing/stale data, distribution shift, malformed outputs, runtime failure, and model-version mismatch.
6. Store immutable evaluation evidence and require independent promotion approval before downstream signal integration.
7. Paper/shadow validation precedes any production use. Live execution remains separately gated and OFF.

## Test coverage
Negative and positive contract tests cover valid evidence output, short windows, look-ahead, timestamp order, stale sequences, nonfinite features, invalid hashes/metadata, malformed probabilities, neutral/low-confidence abstention, and model-runtime failure.

## Compatibility
The result is evidence-only. The existing Signal Agent and Risk Gate remain authoritative. Unknown/abstain never becomes a LONG/SHORT signal by default.
