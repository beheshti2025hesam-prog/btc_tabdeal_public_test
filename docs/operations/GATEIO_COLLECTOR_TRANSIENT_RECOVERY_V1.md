# Gate.io collector transient recovery v1


## 2026-11-13 steady-state resilience hardening

- A live soak showed 1m stale rejection after a two-minute period where both the REST reconciliation path and WebSocket session experienced transient timeouts. The strict 120-second freshness gate was retained.
- The 1m collector previously downloaded a 1,500-candle history on every 20-second reconciliation (two REST requests each time). The 1,500-candle two-page fetch is now bootstrap-only; once a persisted last candle exists, the collector requests a single REST page beginning two candles before the last persisted open time and ending at the current time. This preserves overlap/conflict detection, native schema validation, gap rejection and append-only persistence while reducing routine REST calls and payload size substantially.
- The WebSocket loop now sends Gate's documented unauthenticated `spot.ping` application heartbeat every 15 seconds, consumes `spot.pong` responses, and reconnects on Gate's documented `spot.system` upgrade notification. Read timeout is 5 seconds so heartbeat and periodic reconciliation checks are serviced promptly.
- No stale limit is relaxed; no alternative exchange, data endpoint, synthetic candle or WS-derived OHLCV persistence is introduced.
