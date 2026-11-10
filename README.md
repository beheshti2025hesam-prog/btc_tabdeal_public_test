# HES Trade Agent

**Owner:** Seyed Hesameddin Beheshti Shirazi

> **Exchange decision (2026-10-17): Wallex replaces Tabdeal as the active target for current market-data/WebSocket work.** This repository name and the existing Tabdeal collector are legacy context, not a decision to keep using Tabdeal. Do not treat the Wallex live probe as proof that the repository adapter has already been migrated. See [Exchange Selection DNA & Wallex Checkpoint](docs/architecture/EXCHANGE_SELECTION_DNA_AND_WALLEX_CHECKPOINT_2026-10-17.md).

## Language

- Default application language: **English**
- Supported localization architecture: **English (en)** and **Persian (fa)**
- Additional languages can be added without changing the application core.
- UI localization is designed to support LTR/RTL presentation where applicable.

## Existing collector (legacy)

The current code in this repository includes the original Tabdeal BTC/USDT futures market-data collector. This is historical implementation context; **Wallex is the selected venue for the next exchange-adapter work**. Do not assume code migration is complete until the actual adapter, tests, and exact-head CI have been inspected and verified.

- This legacy collector does NOT use Binance
- It does NOT require a Tabdeal API key
- It does NOT access account balances
- It does NOT place orders
- It does NOT trade

## Active venue evidence

A read-only probe verified the public Wallex WebSocket endpoint `wss://api.wallex.ir/ws` and captured a fresh `BTCUSDT@trade` event on 2026-10-17. Trade identity/sequence, gap-free delivery, replay/recovery, and in-Iran connectivity during an international outage remain unverified. No collector promotion, deployment, or trading is authorized by this probe. Keep **HOLD / NO-TRADE**.

## Ownership / attribution

**HES Trade Agent**  
**Owner: Seyed Hesameddin Beheshti Shirazi**
