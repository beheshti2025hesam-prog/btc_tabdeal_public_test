# HES Trade Agent

**Owner:** Seyed Hesameddin Beheshti Shirazi

## Language

- Default application language: **English**
- Supported localization architecture: **English (en)** and **Persian (fa)**
- Additional languages can be added without changing the application core.
- UI localization is designed to support LTR/RTL presentation where applicable.

## Current data-collection component

This repository contains the first Tabdeal BTC/USDT futures market-data collector used by the **HES Trade Agent** project.

- does NOT require a Tabdeal API key
- does NOT access account balances
- does NOT place orders
- does NOT trade

The archived collector records public Tabdeal BTC_USDT futures trade data for the Data Foundation phase. These trade-tape files are not the canonical global OHLCV candle source for strategy analysis or Transformer training.

## Ownership / attribution

**HES Trade Agent**  
**Owner: Seyed Hesameddin Beheshti Shirazi**

## Transformer Agent v1 (candidate / not production-approved)

- [Inference contract](forward/TRANSFORMER_AGENT_V1.md): model evidence boundary, fail-closed validation, and Signal Agent/Risk Gate authority.
- [Training and evaluation pipeline](forward/TRANSFORMER_TRAINING_V1.md): causal Transformer training, purged chronological splits, train-only normalization, artifact hashing, and test metrics.
- `forward/transformer_torch_adapter_v1.py`: loads a checkpoint only after SHA-256 verification and exposes normalized probabilities through the existing inference contract.
- `tests/test_transformer_agent_v1.py` and `tests/test_transformer_training_v1.py`: negative contract tests plus synthetic-fixture training/checkpoint integration tests.
- `.github/workflows/transformer-training-pipeline.yml`: CPU PyTorch CI for the contract and training pipeline.
- **No real-market model is promoted.** Existing repository CSV archives are trade tape, not canonical global OHLCV candles; synthetic fixtures prove code behavior only. Real OHLCV source provenance, pre-registered fee/slippage neutral band, genuine OOS comparison, calibration, independent review, and paper/shadow validation remain required.
- The component is evidence-only. It cannot place orders or bypass the existing Signal Agent, Confirmation chain, or Risk Gate.
- [Master checkpoint — Transformer Agent, 2026-10-24](docs/checkpoints/MASTER_CHECKPOINT_2026-10-24_TRANSFORMER.md).
