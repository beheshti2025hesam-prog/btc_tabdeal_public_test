# Wallex Read-Only Market Data Adapters v1

Isolated, read-only integration for Wallex Spot markets.

## Official public endpoints

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent-trade window: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Real-time WebSocket: `wss://api.wallex.ir/ws`
- Subscribe frame: `["subscribe", {"channel": "SYMBOL@trade"}]`
- Trade frame: `["SYMBOL@trade", {"isBuyOrder": true, "quantity": "...", "price": "...", "timestamp": "..."}]`

The raw WebSocket protocol is used; do not substitute the legacy Socket.IO client documentation. The WebSocket collector accepts a configured uppercase market symbol and is disabled by default.

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

## Live verification evidence

- REST markets, depth, and latest-trades endpoints returned HTTP 200 with `success=true`. BTCUSDT was present; depth returned 50 asks and 50 bids; the latest-trades endpoint returned 50 records, all 50 normalized successfully.
- Raw WebSocket handshake succeeded. Subscriptions to BTCUSDT depth channels produced live frames.
- A bounded 30-second run of `WallexReadOnlyCollectorV1(symbol="USDTTMN", enabled=True)` received 4 frames, persisted 3 valid trade observations, rejected 0, and ignored 1 non-trade/handshake frame. Persisted records retained `sequence: null`.
- The BTCUSDT trade channel did not emit a trade frame during a separate 115-second bounded sample. The REST latest-trade window's newest timestamp was about 13 minutes old at the time of that check. Therefore the generic Wallex WebSocket transport and trade payload are verified, but **BTCUSDT trade-event freshness remains unverified**.

## Use

For a bounded REST observation run, instantiate `WallexRestWindowCollectorV1(enabled=True, interval_seconds=15, max_runtime_seconds=60)`. For real-time trades, instantiate `WallexReadOnlyCollectorV1(symbol="BTCUSDT", enabled=True, max_runtime_seconds=60)` only after confirming that the configured market emits fresh trade events. Neither collector can place orders.

## Production acceptance gates

1. Focused CI is green on the final commit.
2. Confirm fresh `BTCUSDT@trade` frames from the intended runtime network; investigate the quiet/stale symbol feed before treating it as strategy input.
3. Verify freshness, disconnect/reconnect behavior, heartbeat handling, and durable JSONL records.
4. Confirm downstream ingestion handles unknown sequence semantics without inventing IDs or treating timestamps as sequence.
5. Keep execution disabled until source identity, coverage, and runtime safety gates are independently satisfied.
