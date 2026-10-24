# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Inference contract, reproducible training code, verified checkpoint adapter, and a manual global-OHLCV candidate workflow are implemented. Real-market model promotion remains HOLD.** No genuine market model has been trained or promoted yet. The repository's existing CSV archives are trade tape rather than canonical global OHLCV candles, and the pre-registered neutral-return band from execution fees/slippage is not yet established.

## Reuse-first canonical path
Existing public Binance USDⓈ-M OHLCV adapter → closed-candle export + source hashes → Transformer training/evaluation → verified checkpoint adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No new market-data collector or order route is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: fail-closed evidence-only inference contract.
- `forward/transformer_training_v1.py`: OHLCV-only reader, causal feature representation, explicit future-return labels, purged chronological train/validation/test splits, train-only normalization, causal Transformer training, validation-loss checkpoint selection, test accuracy/class recall/ECE, and hashed manifest.
- `forward/transformer_torch_adapter_v1.py`: verifies model SHA-256 and schema, then emits normalized probabilities through the existing contract.
- `scripts/export_binance_ohlcv_for_transformer_v1.py`: reuses the existing Binance USDⓈ-M public candle adapter, exports closed BTCUSDT candles, aborts on detected gaps, and records per-response and final dataset hashes.
- `tests/test_transformer_agent_v1.py` and `tests/test_transformer_training_v1.py`: malformed-input tests, trade-tape rejection, chronological split controls, synthetic training smoke test, checkpoint integrity, and inference integration.
- `.github/workflows/transformer-agent-contract.yml`, `.github/workflows/transformer-training-pipeline.yml`, and `.github/workflows/transformer-binance-candidate.yml`: contract CI, CPU PyTorch training CI, and manual real-source candidate training with provenance artifact upload.
- `forward/TRANSFORMER_AGENT_V1.md` and `forward/TRANSFORMER_TRAINING_V1.md`: architecture, training method, invocation, and evidence limits.

## Verification status
- Previous inference-contract CI passed on tested code SHA `9312db0a4596d3bdad82d97736114498e8d0c240`: [run 40072369820](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40072369820).
- Latest inference contract run after training changes passed: [run 40072848505](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40072848505).
- Training pipeline tests passed, including the synthetic Transformer training/checkpoint integration: [run 40072848537](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40072848537).
- The new Binance candidate workflow is manual and has not been run. The passing synthetic fixture is software validation only, not real-market performance evidence.

## Remaining evidence gate
1. Pre-register neutral band from documented execution fees/slippage; do not invent a value.
2. Run `.github/workflows/transformer-binance-candidate.yml` with that approved band. It downloads closed BTCUSDT USDⓈ-M 15m candles via the existing adapter and uploads source/model manifests and artifacts.
3. Review immutable test/OOS results against the existing strategy and naive baselines, net of costs; inspect calibration, abstention, drawdown, turnover, and regime stability.
4. Obtain independent promotion approval and run paper/shadow validation before any downstream use.

The trainer rejects the existing Tabdeal trade-tape CSV files; do not bypass the user's global OHLCV source rule. No real model weights, calibrated probabilities, or profitability claim exist until the manual workflow and independent evaluation actually complete.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed.
- PR #364 remains Draft/HOLD. Live execution remains OFF.
