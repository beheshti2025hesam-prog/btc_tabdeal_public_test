# HES Global Market Data — Gate.io Public Feed

- Public, unauthenticated REST candles and WebSocket candle updates; no API key or trading permissions.
- Source endpoints: https://api.gateio.ws/api/v4/spot/candlesticks and wss://api.gateio.ws/ws/v4/.
- Symbol: BTC_USDT; timeframes: 15m, 1h, 4h.
- systemd services: hes-global-market-data-gateio.service, hes-global-market-data-gateio-1h.service, hes-global-market-data-gateio-4h.service.
- JSONL outputs under data/forward/; each service bootstraps up to 500 recent candles, stores closed candles only, deduplicates by candle open time, reconciles REST every 20 seconds, and reconnects with bounded exponential backoff.
- global_market_data_reader_v1.py is a fail-closed input boundary: source identity, OHLC, monotonic order, duplicates, gaps, closed-candle status, minimum history and freshness are checked before a caller can consume the data.

## Important source distinction

Gate.io is a global exchange feed, not an independent multi-exchange aggregate. It is the free, unauthenticated source currently verified reachable from this VPS and supplies the required 15m/1h/4h OHLCV. This does not mean its volume equals another venue's volume. Execution adapters remain separate.

The feed is data-only. It does not place orders or activate a trading strategy. The analysis runtime must explicitly consume load_market_input() before this source can be considered fully wired into strategy decisions.
