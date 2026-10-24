# Transformer Agent v1 — Contract and Promotion Boundary

Status: **inference contract and a reproducible training/adapter pipeline implemented; real-market model promotion remains HOLD**.

## Reuse rule
The Transformer Agent sits behind the existing feature and evidence contracts. It does not replace the canonical OHLCV source, existing data/feature pipeline, Signal Agent, Risk Gate, Mother Orchestrator, or execution boundary. No second market-data collector or order route is introduced.

## Responsibilities
- Accept a fixed ordered feature window and explicit feature names/schema version.
- Require a model version and SHA-256, source SHA-256, and observation timestamp.
- Reject missing or malformed metadata, short windows, mismatched row widths, nonnumeric/nonfinite values, duplicate/nonmonotonic timestamps, stale windows, and any timestamp later than the observation (look-ahead).
- Invoke a predictor adapter for a trained model/runtime; validate exactly three normalized probabilities: LONG, SHORT, NEUTRAL.
- Return either EVIDENCE_ONLY or ABSTAIN/UNKNOWN with machine-readable reason codes and sequence lineage hash.
- Never create a trade order, bypass Signal Agent, or authorize execution.

## Implemented model lifecycle
- `forward/transformer_training_v1.py`: train/evaluation pipeline for a small causal Transformer using approved canonical OHLCV CSV; chronological purged splits, train-only normalization, validation-loss checkpoint selection, test metrics, and a manifest containing source/model hashes.
- `forward/transformer_torch_adapter_v1.py`: verifies checkpoint SHA-256 and feature/class schema before loading it into the existing inference contract.
- `forward/TRANSFORMER_TRAINING_V1.md`: source contract, invocation example, leakage controls, and remaining data gates.
- `tests/test_transformer_training_v1.py`: synthetic-fixture training smoke test, split-purge tests, trade-tape rejection, artifact hash verification, and inference integration.
- `.github/workflows/transformer-training-pipeline.yml`: dedicated CPU PyTorch CI.

## Evidence boundary — important
The repository's current `data/trades.csv` and `data/archive/*.csv` are trade-tape files, not the canonical global OHLCV candle dataset required for this model. Synthetic fixtures test code behavior only. No genuine market model weights, calibrated probabilities, or real-market out-of-sample performance are claimed. A source ID in a manifest is an operator declaration; it does not by itself independently authenticate the provider.

The 0.60 default in the generic inference contract is only an abstention threshold, not a claim of 60% win probability or calibrated confidence.

## Evaluation / promotion sequence
1. Supply a verified, closed-candle OHLCV export from the approved canonical global provider; freeze its file hash and source/timeframe metadata.
2. Pre-register the target horizon and neutral-return band from documented fees/slippage; do not tune toward a desired win rate.
3. Train with the reproducible script and preserve the model plus manifest hashes.
4. Compare against the existing strategy and naive baselines on identical immutable data; include net-of-fee/slippage outcomes, calibration, coverage/abstention, drawdown, turnover, and regime stability.
5. Run adversarial tests for missing/stale data, distribution shift, malformed outputs, runtime failure, and model-version mismatch.
6. Store immutable OOS evidence and require independent promotion approval before downstream signal integration.
7. Run paper/shadow validation before any production use. Live execution remains separately gated and OFF.

Unknown/abstain never becomes a LONG/SHORT signal by default.
