# Transformer Agent v1 — Training and Evaluation Pipeline

Status: **implemented and testable; no real-market model is promoted**.

## What this adds
- `forward/transformer_training_v1.py`: reads chronologically ordered OHLCV candles, builds a small causal Transformer, creates explicit SHORT/NEUTRAL/LONG labels from a future-return horizon, performs purged chronological train/validation/test splits, fits normalization on training rows only, and emits a checkpoint plus SHA-256 manifest.
- `forward/transformer_torch_adapter_v1.py`: verifies checkpoint SHA-256, validates the saved feature/class schema, loads the model, and returns normalized probabilities through the existing Transformer Agent predictor contract.
- `tests/test_transformer_training_v1.py`: tests rejection of trade-tape CSV, chronological split boundaries, training/checkpoint creation, artifact verification, and contract integration.
- `.github/workflows/transformer-training-pipeline.yml`: installs CPU-only PyTorch in CI and runs both inference-contract and training-pipeline tests.

## Input contract
CSV columns required: `timestamp,open,high,low,close,volume`. Timestamps must be timezone-aware and strictly increasing. Rows must be closed candles from the project's approved canonical global OHLCV provider. Raw trade tape, including `price/amount/side/sequence`, is explicitly rejected. The CLI requires the operator to state source ID, candle interval, forecast horizon, and neutral band in basis points; the neutral band must be chosen from a separately evidenced fee/slippage policy, not optimized to a desired win rate.

Example (only after obtaining and verifying an approved global OHLCV export):

```bash
python -m pip install torch
python forward/transformer_training_v1.py \
  --input /path/to/verified_btcusdt_15m_ohlcv.csv \
  --source-id binance-public-spot \
  --interval 15m \
  --horizon 3 \
  --neutral-band-bps <pre-registered-fee-and-slippage-band> \
  --sequence-length 32 \
  --epochs 20 \
  --output-dir artifacts/transformer-candidate
```

The placeholder must be replaced with the already-approved numeric basis-point value. Do not use the Tabdeal trade-tape archive as a substitute for global OHLCV candles.

## Leakage controls and output
- Feature windows are causal and end at the sample timestamp.
- Targets use the future close at the explicit horizon.
- Train/validation/test are chronological; samples whose target horizons cross split boundaries are purged.
- Normalization is fitted only on training-period rows.
- The test split is never used for early stopping; best checkpoint is selected by validation cross-entropy.
- The manifest records source ID and file hash, interval, target policy, split counts, model hash, test accuracy, class recall, expected calibration error, and HOLD status.
- The model is always marked `RESEARCH_CANDIDATE_NOT_PROMOTED`; metrics are descriptive and not a claim of profitability.

## Important current limitation
The repository's historical `data/trades.csv` and `data/archive/*.csv` are trade-tape data, not the canonical global OHLCV candle dataset required for this model. The new pipeline is exercised using synthetic fixtures solely to verify code behavior. **No real-market Transformer weights or genuine OOS performance evidence have been produced by these tests.** A verified global OHLCV export and a pre-registered fee/slippage neutral band are still required before a real candidate can be trained and assessed.

## Promotion remains blocked
A trained artifact must still beat the existing strategy and naive baselines on identical immutable data, after fees/slippage, and show acceptable calibration, abstention coverage, drawdown, turnover, and regime stability. Independent review and paper/shadow validation remain mandatory. This pipeline does not connect to the VPS or execution path.
