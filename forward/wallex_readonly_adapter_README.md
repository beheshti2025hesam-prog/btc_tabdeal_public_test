# Wallex Read-Only Market Data Adapter v1

Isolated, read-only integration for Wallex Spot `BTCUSDT`.

## Official public endpoints

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent-trade window: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Real-time WebSocket: `wss://api.wallex.ir/ws`
- Subscribe frame: `["subscribe", {"channel": "BTCUSDT@trade"}]`
- Trade event frame: `["BTCUSDT@trade", {"isBuyOrder": true, "quantity": "...", "price": "...", "timestamp": "..."}]`

The raw WebSocket protocol is used; do not substitute the legacy Socket.IO client documentation.

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
- Uses the existing `websocket-client` dependency; no extra Socket.IO dependency.

## Verified in this change

- Live public REST requests to markets, depth, and recent trades returned HTTP 200 with `success=true`.
- BTCUSDT market metadata was present; depth returned 50 asks and 50 bids; latest trades returned 50 records, all 50 normalized successfully in the bounded check.
- The focused automated suite passed before the raw-WebSocket transport correction; rerun CI after the correction.
- A raw WebSocket handshake to `wss://api.wallex.ir/ws` succeeded and depth-channel subscription produced live frames. The trade channel must be validated separately by observing at least one actual trade frame.

## Use

For a bounded REST observation run, instantiate `WallexRestWindowCollectorV1(enabled=True, interval_seconds=15, max_runtime_seconds=60)`. For real-time trades, use `WallexReadOnlyCollectorV1(enabled=True, max_runtime_seconds=60)` only after a bounded live capture confirms trade frames. Neither collector can place orders.

## Production acceptance gates

1. Focused CI is green on the final commit.
2. Confirm at least one real `BTCUSDT@trade` frame and verify the payload fields.
3. Verify freshness, bounded reconnect behavior, heartbeat handling, and durable JSONL records.
4. Confirm downstream ingestion handles unknown sequence semantics without inventing IDs or treating timestamps as sequence.
5. Keep execution disabled until source identity, coverage, and runtime safety gates are independently satisfied.
