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
## Integrated read-only market dashboard

The project includes a first integrated dashboard slice in `web/dashboard.py`. It is intentionally read-only and binds to loopback by default; it does not expose account access or order submission.

```bash
PYTHONPATH=. python -m web.dashboard
```

Open `http://127.0.0.1:8765` on the same host. To change the local bind port, set `HES_DASHBOARD_PORT`. Do not bind to a public interface or expose it through a reverse proxy without separately reviewed authentication and network controls.

Chart candles currently use Yahoo Finance's public chart endpoint as an **unverified USD reference only**—not as a certified global aggregate or approved strategy input, and never from the execution venue's chart API. The endpoint is unofficial, has no guaranteed SLA, and its aggregation and volume semantics are not verified. Only validated, closed and fresh candles are shown; source volume is preserved unchanged. Do not enable volume-derived features or feed this source into strategy decisions until provider provenance, volume meaning, freshness, and independent chart comparisons are proven. The dashboard remains `HOLD / NO_TRADE_ONLY` and has no order-submit endpoint. This UI slice does not mean the private execution adapter or live trading is ready.
