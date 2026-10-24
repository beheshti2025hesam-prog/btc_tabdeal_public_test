# HES Trade Agent

**Owner:** Seyed Hesameddin Beheshti Shirazi

## Language

- Default application language: **English**
- Supported localization architecture: **English (en)** and **Persian (fa)**
- Additional languages can be added without changing the application core.
- UI localization is designed to support LTR/RTL presentation where applicable.

## Current data-collection component

This repository contains the first Tabdeal BTC/USDT futures market-data collector used by the **HES Trade Agent** project.

- does NOT use Binance
- does NOT require a Tabdeal API key
- does NOT access account balances
- does NOT place orders
- does NOT trade

It collects public Tabdeal BTC_USDT futures trade data for the Data Foundation phase.

## Ownership / attribution

**HES Trade Agent**  
**Owner: Seyed Hesameddin Beheshti Shirazi**


## Transformer Agent v1 (candidate / not production-approved)

- [Transformer Agent contract](forward/TRANSFORMER_AGENT_V1.md) defines the model-agnostic, evidence-only inference boundary.
- `forward/transformer_agent_v1.py` validates sequence freshness, causal timestamps, finite feature rows, source/model hashes, versioned feature schema, and normalized LONG/SHORT/NEUTRAL output from an injected existing model adapter.
- Unknown, neutral, malformed, stale, look-ahead, or model-runtime failure cases abstain to UNKNOWN; the component cannot place orders or bypass the Signal Agent and Risk Gate.
- No Transformer architecture, weights, training data, calibration, or profitability is fabricated. A real model must pass reproducible out-of-sample/walk-forward evaluation before promotion.
- [Master checkpoint — Transformer Agent, 2026-10-24](docs/checkpoints/MASTER_CHECKPOINT_2026-10-24_TRANSFORMER.md).
