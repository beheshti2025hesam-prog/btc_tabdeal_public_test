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

## Live execution boundary (not enabled)

- [Live Execution Boundary v1](docs/execution/LIVE_EXECUTION_BOUNDARY_V1.md) defines the required fail-closed preflight and promotion sequence.
- [Master checkpoint — live execution, 2026-10-24](docs/checkpoints/MASTER_CHECKPOINT_2026-10-24_LIVE_EXECUTION.md) records the current state and remaining acceptance gates.
- `forward/execution_gate_v1.py` is a preflight contract only; it cannot submit orders.
- `forward/execution_journal_v1.py` provides a durable SQLite idempotency/state journal and blocks automatic retry of ambiguous submissions until explicit reconciliation evidence is recorded.
- No concrete venue adapter, credentials, or order route exists in this candidate. Runtime defaults deny live execution; passing unit tests does not authorize production trading.

- `forward/execution_adapter_contract_v1.py` is the single typed venue-adapter contract, including symbol mapping, order lifecycle snapshots, and externally pinned capability evidence. It is an interface/validation contract, not a concrete exchange integration.
- `tests/test_execution_adapter_contract_v1.py` runs with the execution gate and journal suite in the dedicated workflow.
- A concrete adapter remains blocked until an execution venue is approved from authoritative evidence and independently reviewed; do not infer approval from the generic contract or CI.
