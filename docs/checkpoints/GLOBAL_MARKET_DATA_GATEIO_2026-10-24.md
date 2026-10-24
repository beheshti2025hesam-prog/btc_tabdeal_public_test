# HES Global Market Data Gate.io Checkpoint — 2026-10-24

## Decision
Use Gate.io's public, unauthenticated spot market-data endpoints as the currently reachable free candle source from this VPS. Binance REST is blocked/timeout from this host; CoinGecko is reachable but its free API does not provide the required 15m OHLCV cadence. Gate.io is a single-exchange source, not a cross-exchange aggregate.

## Implemented on VPS
- Adapter: forward/global_market_data_gateio_v1.py
- Reader boundary: forward/global_market_data_reader_v1.py
- Entrypoint: scripts/run_global_market_data_gateio_service.py
- systemd units: hes-global-market-data-gateio.service (15m), hes-global-market-data-gateio-1h.service (1h), hes-global-market-data-gateio-4h.service (4h)
- Outputs: data/forward/global_market_candles_v1.jsonl, data/forward/global_market_candles_1h_v1.jsonl, data/forward/global_market_candles_4h_v1.jsonl
- Bootstrap: up to 500 recent candles per timeframe; only closed candles are persisted.
- Recovery: WebSocket reconnect with bounded backoff and REST reconciliation while connected.
- Safety: no API keys, private account access, order placement, or strategy activation.

## Verified
- Public REST candle request returned HTTP 200 from the VPS.
- Public WebSocket candle subscription returned status success.
- All three systemd services are enabled and active at the checkpoint.
- 15m/1h/4h output each contains 499 closed candles; timestamps are strictly increasing and contiguous in the checked window; no duplicates; OHLC bounds validated.
- Unit tests: 10/10 passed across the feed adapter and fail-closed reader tests.
- Reader smoke test accepted all three timeframes and returned hes_global_market_input_v1.
- Previous 9-row 15m bootstrap is preserved at data/forward/global_market_candles_v1.prebootstrap_backup.jsonl.

## Architecture boundary / not yet complete
The source and validated market-input reader are running, but the existing decision/runtime pipeline has not yet been switched to consume load_market_input() end-to-end. The only accessible GitHub repository is btc_tabdeal_public_test; no separate frontend repository was visible to the connected GitHub account. Therefore chart/UI wiring and decision-engine adoption are not claimed complete.

## Required next gates
1. Wire the validated multi-timeframe input into the actual analysis/runtime entrypoint without using Tabdeal candles/trade sequence as analysis input.
2. Confirm the frontend repo/entrypoint if chart display is part of release scope.
3. Run a 24-hour soak and verify fresh closed candles, reconnect recovery, gap/staleness vetoes, and service restart behavior.
4. Keep trading/live execution disabled until separate evidence and risk gates pass.
