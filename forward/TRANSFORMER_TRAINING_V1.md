# Transformer Agent v1 — Training and Evaluation Pipeline

Status: **training code and source-export workflow implemented; real-market model promotion remains HOLD**.

## What this adds
- `forward/transformer_training_v1.py`: reads chronologically ordered OHLCV candles, builds a small causal Transformer, creates explicit SHORT/NEUTRAL/LONG labels from a future-return horizon, performs purged chronological train/validation/test splits, fits normalization on training rows only, and emits a checkpoint plus SHA-256 manifest. If a documented round-trip fee+slippage cost is supplied, it also calculates a non-overlapping test-split strategy summary (trade coverage, gross/net mean bps, net-positive trade rate, compounded net return, and drawdown); otherwise it explicitly records that the strategy backtest was not run.
- `forward/transformer_torch_adapter_v1.py`: verifies checkpoint SHA-256, validates the saved feature/class schema, loads the model, and returns normalized probabilities through the existing Transformer Agent predictor contract.
- `scripts/export_binance_ohlcv_for_transformer_v1.py`: reuses the existing `BinanceUsdMPerpetualKlineSource` adapter to export closed BTCUSDT USDⓈ-M 15m candles. It records per-response hashes, final CSV hash, date range, and candle count; any observed candle gap aborts the export.
- `tests/test_transformer_training_v1.py`: tests rejection of trade-tape CSV, candle gaps and misaligned timestamps, chronological split boundaries, training/checkpoint creation, artifact verification, and contract integration.
- `tests/test_transformer_binance_export_v1.py`: mocked pagination test for the existing Binance adapter exporter, CSV/hash-manifest verification, and fail-closed gap rejection.
- `.github/workflows/transformer-training-pipeline.yml`: CPU PyTorch CI for the inference and training contracts.
- `.github/workflows/transformer-binance-candidate.yml`: manually triggered, read-only Binance data export + candidate training + provenance artifact upload. Both the neutral-label band and round-trip cost (documented fees plus evidenced slippage for the intended execution venue) are required inputs, not guessed defaults.

## Input contract
CSV columns required: `timestamp,open,high,low,close,volume`. Timestamps must be timezone-aware and strictly increasing. Rows must be closed candles from the approved canonical global OHLCV provider. Raw trade tape, including `price/amount/side/sequence`, is explicitly rejected. The CLI requires source ID, candle interval, forecast horizon, and neutral band in basis points. The optional `--round-trip-cost-bps` input enables strategy-level test metrics and must be backed by documented fees plus evidenced slippage for the intended execution venue. Do not substitute Binance fees for an unconfirmed Iranian venue, and do not optimize either input toward a desired win rate.

The exporter reuses the existing public Binance USDⓈ-M perpetual OHLCV adapter; it does not add a second market-data implementation, require API credentials, access accounts, place orders, or activate a collector.

## Reproducible training
For a manually downloaded and independently verified export:

```bash
python -m pip install torch
python forward/transformer_training_v1.py \
  --input /path/to/verified_btcusdt_15m_ohlcv.csv \
  --source-id binance-usdm-perpetual-public-klines \
  --interval 15m \
  --horizon 3 \
  --neutral-band-bps <pre-registered-neutral-label-band> \
  --round-trip-cost-bps <documented-round-trip-fees-plus-slippage> \
  --sequence-length 32 \
  --epochs 20 \
  --output-dir artifacts/transformer-candidate
```

Replace both placeholders with approved numeric values. The neutral band defines labels; round-trip cost is separately subtracted in the strategy-level test evaluation. To export a fresh source snapshot using the existing adapter, run `python scripts/export_binance_ohlcv_for_transformer_v1.py --days 180 --interval 15m`. The manual GitHub Actions workflow performs this export and uploads the dataset, source manifest, model, and training manifest as one artifact.

## Leakage controls and output
- Feature windows are causal and end at the sample timestamp.
- Targets use the future close at the explicit horizon.
- Train/validation/test are chronological; samples whose target horizons cross split boundaries are purged.
- Normalization is fitted only on training-period rows.
- The test split is never used for early stopping; best checkpoint is selected by validation cross-entropy.
- The manifest records source ID and file hash, interval, target policy, split counts, model hash, test accuracy, class recall, expected calibration error, optional cost-aware strategy test metrics, and HOLD status.
- The model is always marked `RESEARCH_CANDIDATE_NOT_PROMOTED`; metrics are descriptive and not a claim of profitability.

## Important current limitation
The repository's historical `data/trades.csv` and `data/archive/*.csv` are trade-tape data, not the canonical global OHLCV candle dataset required for this model. The new pipeline is exercised using synthetic fixtures solely to verify code behavior. **No real-market Transformer weights or genuine OOS performance evidence have been produced by these tests.** The manual Binance training workflow is ready but has not been run; a pre-registered fee/slippage neutral band is still required.

## Promotion remains blocked
A trained artifact must still beat the existing strategy and naive baselines on identical immutable data, after fees/slippage, and show acceptable calibration, abstention coverage, drawdown, turnover, and regime stability. Independent review and paper/shadow validation remain mandatory. This pipeline does not connect to the VPS or execution path.
