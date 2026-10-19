# HES Trade Agent

**Owner:** Seyed Hesameddin Beheshti Shirazi

## Language

- Default application language: **English**
- Supported localization architecture: **English (en)** and **Persian (fa)**
- Additional languages can be added without changing the application core.
- UI localization is designed to support LTR/RTL presentation where applicable.

## Current project source and legacy collector

**Active exchange decision (2026-10-17): Wallex** is the approved target for current public market-data and WebSocket work. The repository name and older Tabdeal collector references are historical identifiers, not authorization to treat Tabdeal as the active source. See the project’s exchange-selection DNA and current GitHub checkpoints before any exchange-specific change.

The original Tabdeal BTC_USDT Futures collector is legacy/historical context. Do not silently switch back to Tabdeal or relabel data from one venue as another. Any alternate venue requires an explicit project decision.

Current safety boundary:

- public/read-only market data only unless a separate gate explicitly authorizes otherwise
- no account-balance access or authenticated account mutation for this data-foundation work
- no order placement or trading
- native OHLCV candles are preferred for candle-based analysis; do not reconstruct them from individual trades or sequence IDs by default
- sequence/order-flow validation is separate and conditional on features that genuinely require trade-level identity or ordering

## Ownership / attribution

**HES Trade Agent**  
**Owner: Seyed Hesameddin Beheshti Shirazi**
