# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Inference contract, actual training code, verified checkpoint adapter, canonical Binance OHLCV exporter, and cost-aware first-pass test simulation are implemented.** Contract and training/exporter tests passed, including the synthetic training/checkpoint integration. Real-market model promotion remains HOLD: no genuine market candidate has yet been trained, and the cost policy must come from the intended execution venue's documented fees plus evidenced slippage.

## Reuse-first canonical path
Existing public Binance USDⓈ-M OHLCV adapter → closed-candle export + source hashes → Transformer training/evaluation → verified checkpoint adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No new market-data collector or order route is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: fail-closed evidence-only inference; binds model hash/version/feature schema to predictor metadata where available.
- `forward/transformer_training_v1.py`: OHLCV-only reader; rejects trade tape, candle gaps/overlaps, and timestamps not aligned to UTC candle boundaries; causal features; explicit future-return labels; purged chronological train/validation/test splits; train-only normalization; causal Transformer; validation-loss checkpoint selection; test accuracy/class recall/ECE; hashed manifest.
- The trainer optionally calculates a first-pass, non-overlapping horizon strategy summary on the test split when documented round-trip cost is provided: signal coverage, gross/net mean return per trade, net-positive trade rate, compounded net return, and drawdown. This is not a full walk-forward/production backtest.
- `forward/transformer_torch_adapter_v1.py`: verifies model SHA-256 and saved feature/class schema before inference.
- `scripts/export_binance_ohlcv_for_transformer_v1.py`: reuses the existing Binance USDⓈ-M public candle adapter, exports closed BTCUSDT candles, aborts on gaps, and records per-response and final dataset hashes.
- `tests/test_transformer_agent_v1.py`, `tests/test_transformer_training_v1.py`, and `tests/test_transformer_binance_export_v1.py`: fail-closed contract tests, synthetic training/checkpoint integration, cost-aware evaluation validation, trade-tape/gap/alignment rejection, exporter pagination/hash manifest, and gap rejection.
- `.github/workflows/transformer-agent-contract.yml`, `.github/workflows/transformer-training-pipeline.yml`, and `.github/workflows/transformer-binance-candidate.yml`: contract CI, CPU PyTorch tests, and manual source-export/candidate training with source/model artifact upload. The candidate workflow now requires both neutral-label band and round-trip cost inputs.

## Verification
- Contract CI passed with the current Transformer contract and training tests: [run 40075768028](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075768028).
- Training/exporter pipeline passed on code/test state SHA `e2c058633a9f4fe7fa430a7e5d5aee09355bb4b8`, including Python compilation, synthetic Transformer training, cost-aware test simulation, exporter pagination/hash tests, and fail-closed gap checks: [run 40075765007](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40075765007).
- Later commits updated docs and removed duplicate push-triggered CI configuration; model/training code and tests were unchanged after the successful run.
- The manual Binance candidate workflow has not been run. Synthetic fixtures/mock exporter responses are software validation only, not real-market performance evidence.

## Remaining evidence gate
1. Confirm the intended execution venue and pre-register the neutral-label band and round-trip cost using documented fees plus evidenced slippage. Do not substitute Binance fees for an unconfirmed Iranian venue or invent slippage.
2. Run `.github/workflows/transformer-binance-candidate.yml` with those approved numeric inputs. It exports closed BTCUSDT USDⓈ-M 15m candles via the existing adapter, trains a candidate, and uploads source/model manifests and artifacts.
3. Compare immutable out-of-sample results against the existing strategy and naive baselines, net of costs; inspect calibration, abstention coverage, drawdown, turnover, and regime stability. The included first-pass cost-aware summary does not replace a full walk-forward evaluation.
4. Obtain independent promotion approval and paper/shadow validation before downstream use.

The trainer rejects existing Tabdeal trade-tape CSV files; do not bypass the global OHLCV source rule. No real-market model weights, calibrated probabilities, or profitability claim exist until the real-data workflow and independent evaluation actually complete.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed.
- PR #364 remains Draft/HOLD. Live execution remains OFF.
