# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Inference contract, training code, verified checkpoint adapter, canonical Binance OHLCV exporter, and manual candidate-training workflow implemented.** Contract and training/exporter test suites passed on code SHA `4febd2b8c484bb89030224cb8bd8b140ccdf6d02`. Real-market model promotion remains HOLD because the manual real-data workflow has not yet run and the cost-sensitive label band is not approved from the actual execution venue's documented fees/slippage.

## Reuse-first canonical path
Existing public Binance USDⓈ-M OHLCV adapter → closed-candle export + source hashes → Transformer training/evaluation → verified checkpoint adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No new market-data collector or order route is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: fail-closed evidence-only inference; binds model hash/version/feature schema to predictor metadata where available.
- `forward/transformer_training_v1.py`: OHLCV-only reader; rejects trade tape, candle gaps/overlaps, and timestamps not aligned to UTC candle boundaries; causal features; explicit future-return labels; purged chronological train/validation/test splits; train-only normalization; causal Transformer; validation-loss checkpoint selection; test accuracy/class recall/ECE; hashed manifest.
- `forward/transformer_torch_adapter_v1.py`: verifies model SHA-256 and saved feature/class schema before inference.
- `scripts/export_binance_ohlcv_for_transformer_v1.py`: reuses the existing Binance USDⓈ-M public candle adapter, exports closed BTCUSDT candles, aborts on gaps, and records per-response and final dataset hashes.
- `tests/test_transformer_agent_v1.py`, `tests/test_transformer_training_v1.py`, and `tests/test_transformer_binance_export_v1.py`: fail-closed contract tests, synthetic training/checkpoint integration, trade-tape/gap/alignment rejection, exporter pagination, dataset hash verification, and gap rejection.
- `.github/workflows/transformer-agent-contract.yml`, `.github/workflows/transformer-training-pipeline.yml`, and `.github/workflows/transformer-binance-candidate.yml`: contract CI, CPU PyTorch tests, and manual source-export/candidate training with provenance artifact upload.
- `forward/TRANSFORMER_AGENT_V1.md` and `forward/TRANSFORMER_TRAINING_V1.md`: contracts, lifecycle, training, and evidence boundaries.

## Verification
- Latest contract CI passed on code SHA `4febd2b8c484bb89030224cb8bd8b140ccdf6d02`: [run 40075449358](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075449358).
- Latest training pipeline CI passed on the same code SHA, including Python compilation, synthetic Transformer training, and exporter pagination/gap tests: [run 40075449359](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075449359).
- Earlier runs on the same SHA also passed: [contract run 40075446622](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075446622), [training run 40075446553](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075446553).
- The manual Binance candidate workflow has not been run. Synthetic fixtures/mock exporter responses are software validation only, not real-market performance evidence.

## Remaining evidence gate
1. Establish the intended execution venue and pre-register the neutral-return/cost policy from documented fees plus evidenced slippage. Do not substitute Binance fees for an unconfirmed Iranian venue or invent a slippage value.
2. Run `.github/workflows/transformer-binance-candidate.yml` with the approved numeric band. It exports closed BTCUSDT USDⓈ-M 15m candles through the existing adapter, trains a candidate, and uploads the source/model manifests and artifacts.
3. Compare immutable out-of-sample predictions against the existing strategy and naive baselines, net of costs; inspect calibration, abstention coverage, drawdown, turnover, and regime stability. The current training manifest reports classifier metrics only; a cost-aware strategy-level backtest remains required before promotion.
4. Obtain independent promotion approval and paper/shadow validation before downstream use.

The trainer rejects existing Tabdeal trade-tape CSV files; do not bypass the global OHLCV source rule. No real-market model weights, calibrated probabilities, or profitability claim exist until the real-data workflow and independent evaluation actually complete.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed.
- PR #364 remains Draft/HOLD. Live execution remains OFF.
