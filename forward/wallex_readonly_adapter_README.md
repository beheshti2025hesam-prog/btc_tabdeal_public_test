# Wallex Read-Only Market Data Adapters v1

Isolated, read-only integration for Wallex Spot markets.

## Official public endpoints and protocol

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent-trade window: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Official WebSocket usage: Socket.IO client connected to `https://api.wallex.ir`, with `transports=["websocket"]`
- Subscribe event: `subscribe` with `{"channel":"SYMBOL@trade"}`
- Trade events: `Broadcaster(channel, data)`, where channel is `SYMBOL@trade`

Wallex's published API reference specifies a Socket.IO v2-compatible client. The Python adapter therefore uses `python-socketio==4.6.1`; it does not treat the endpoint as an arbitrary raw WebSocket or send a raw JSON array as a WebSocket frame. The collector accepts a configured uppercase market symbol and is disabled by default.

## Sequence and coverage contract

The documented trade payload does **not** include a per-trade sequence/ID. Both adapters preserve `sequence: null` and `sequence_semantics: NOT_DOCUMENTED_BY_VENUE`. Do not wire them into sequence-dependent candle logic until an independently verified identity policy exists. A raw-payload SHA-256 is only a fingerprint for exact-replay diagnostics, not an exchange identity.

The REST endpoint returns a latest-trades window, not a complete event log. The REST collector labels it `LATEST_WINDOW_ONLY`, polls no faster than once per 15 seconds, and never infers that unseen events were absent. This mode can miss trades between polls and is for observation/market-data validation only.

## Safety

- Disabled by default; explicit `enabled=True` is required.
- Public market data only; no API key is accepted or required.
- No account, wallet, order, or withdrawal APIs.
- Append-only JSONL with flush and fsync.
- No Git operations, no pushes, no writes to `main`, no strategy execution.
- Bounded runtime, strict decimal/symbol/timezone validation, and exact payload fingerprinting.
- Socket.IO client dependency is pinned; no private credentials are used.

## Live verification evidence

- REST markets, depth, and latest-trades endpoints returned HTTP 200 with `success=true`. BTCUSDT was present; depth returned 50 asks and 50 bids; the latest-trades endpoint returned 50 records.
- A fresh REST check at 2026-10-17 10:01:58 UTC returned a newest BTCUSDT trade timestamp of 2026-10-17 10:01:54 UTC (about 4 seconds old).
- A direct raw-WebSocket probe to `wss://api.wallex.ir/ws` returned a handshake-shaped JSON object but no trade events. This is not proof of a successful subscription.
- A Socket.IO v2-compatible client attempt from the VPS did not establish a connection (websocket error); the standard `/socket.io/` path also returned HTTP 503 during the direct probe. Thus **live Socket.IO BTCUSDT trade delivery remains unverified from the intended runtime network**. Do not claim the real-time feed is connected until this is resolved and a fresh `Broadcaster` trade event is captured.
- Focused unit tests exercise the documented `subscribe` / `Broadcaster` contract with a mock client; they do not replace live-network verification.

## Use

For a bounded REST observation run, instantiate `WallexRestWindowCollectorV1(enabled=True, interval_seconds=15, max_runtime_seconds=60)`. For real-time trades, instantiate `WallexReadOnlyCollectorV1(symbol="BTCUSDT", enabled=True, max_runtime_seconds=60)` only after confirming that the Socket.IO connection and configured market emit fresh trade events. Neither collector can place orders.

## Production acceptance gates

1. Focused CI is green on the final commit.
2. Establish a Socket.IO connection from the intended runtime network and capture fresh `BTCUSDT@trade` `Broadcaster` events.
3. Verify freshness, disconnect/reconnect behavior, heartbeat handling, and durable JSONL records.
4. Confirm downstream ingestion handles unknown sequence semantics without inventing IDs or treating timestamps as sequence.
5. Keep execution disabled until source identity, coverage, and runtime safety gates are independently satisfied.
