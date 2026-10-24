# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Inference contract, real training code, checkpoint adapter, global-OHLCV exporter, and manual candidate-training workflow implemented.** The software path is CI-green on code SHA `e09961f9cdcd255fa14c8af8f6d4f794a4ccf1da`. Real-market model promotion remains HOLD because the manual real-data workflow has not yet been run and the neutral-return band must be set from documented execution fees/slippage.

## Reuse-first canonical path
Existing public Binance USDⓈ-M OHLCV adapter → closed-candle export + source hashes → Transformer training/evaluation → verified checkpoint adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No new market-data collector or order route is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: fail-closed evidence-only inference contract. It now binds model hash, model version, and feature schema to predictor metadata when the adapter exposes them.
- `forward/transformer_training_v1.py`: OHLCV-only reader; interval-gap/overlap rejection; causal feature representation; explicit future-return labels; purged chronological train/validation/test splits; train-only normalization; causal Transformer training; validation-loss checkpoint selection; test accuracy/class recall/ECE; hashed manifest.
- `forward/transformer_torch_adapter_v1.py`: verifies model SHA-256 and saved feature/class schema, then emits normalized probabilities through the existing contract.
- `scripts/export_binance_ohlcv_for_transformer_v1.py`: reuses the existing Binance USDⓈ-M public candle adapter, exports closed BTCUSDT candles, aborts on detected gaps, and records per-response and final dataset hashes.
- `tests/test_transformer_agent_v1.py` and `tests/test_transformer_training_v1.py`: malformed-input and artifact-mismatch tests, trade-tape rejection, missing-candle interval rejection, chronological split controls, synthetic training smoke test, checkpoint integrity, and inference integration.
- `.github/workflows/transformer-agent-contract.yml`, `.github/workflows/transformer-training-pipeline.yml`, and `.github/workflows/transformer-binance-candidate.yml`: contract CI, CPU PyTorch training CI, and manual real-source candidate training with provenance artifact upload.
- `forward/TRANSFORMER_AGENT_V1.md` and `forward/TRANSFORMER_TRAINING_V1.md`: architecture, training method, invocation, and evidence limits.

## Verification
- Contract CI passed on current code SHA `e09961f9cdcd255fa14c8af8f6d4f794a4ccf1da`: [run 40073224968](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40073224968).
- Training pipeline CI passed on the same code SHA, including Python compile checks and synthetic training/checkpoint integration: [run 40073225022](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40073225022).
- Earlier training run also passed after the OHLCV interval-gap test: [run 40073180977](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40073180977).
- The manual Binance candidate workflow has not been run. Synthetic fixtures are software tests only, not real-market performance evidence.

## Remaining evidence gate
1. Pre-register the neutral band from documented execution fees/slippage; do not invent a value.
2. Run `.github/workflows/transformer-binance-candidate.yml` with that approved band. It downloads closed BTCUSDT USDⓈ-M 15m candles via the existing adapter and uploads source/model manifests and artifacts.
3. Review immutable test/OOS results against the existing strategy and naive baselines, net of costs; inspect calibration, abstention, drawdown, turnover, and regime stability.
4. Obtain independent promotion approval and run paper/shadow validation before any downstream use.

The trainer rejects existing Tabdeal trade-tape CSV files; do not bypass the global OHLCV source rule. No real model weights, calibrated probabilities, or profitability claim exist until the manual workflow and independent evaluation actually complete.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed.
- PR #364 remains Draft/HOLD. Live execution remains OFF.
