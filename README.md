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


## Read-only dashboard and Signal Agent entry point

The existing dashboard is the application entry surface for the current data-foundation slice; it is not a separate trading application.

- Start locally from the repository root with `python -m web.dashboard` after installing the project requirements and the optional market-data transport dependency in `requirements-market-data.txt`.
- Dashboard: `/`; validated closed-candle API: `GET /api/candles`; Signal Agent evaluation: `GET /api/signal?symbol=BTCUSDT&interval=15m`; health: `/healthz`.
- The Signal Agent route reuses the same native OHLCV batch/cache and feature pipeline as the chart, and returns the source response SHA-256 and gate/block reasons.
- The route intentionally returns `BLOCKED / NO_TRADE` while symbol mapping evidence, validated directional structure, strategy-level signal-quality approval, and provenance-bound entry/stop/target risk geometry are missing. Feature-engine quality is not equivalent to the strategy-level signal-quality gate.
- The dashboard has no order-submit endpoint. WebSocket collection remains opt-in and execution remains disabled. Do not deploy or enable trading from this branch alone.
- See [Signal Agent v1 boundary](forward/SIGNAL_AGENT_V1.md) and [entrypoint integration checkpoint](docs/checkpoints/SIGNAL_AGENT_ENTRYPOINT_INTEGRATION_2026-10-24.md).
