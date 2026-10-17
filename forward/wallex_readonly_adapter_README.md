# Wallex Read-Only Market Data Adapter v1

This is an isolated, read-only integration for Wallex Spot `BTCUSDT`.

## Public contract used

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent-trade window: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Socket.IO public trade channel: `BTCUSDT@trade`, event `Broadcaster(channel, data)`
- Documented trade fields: `price`, `quantity`, `isBuyOrder`, `timestamp`

## Sequence and coverage contract

Wallex's documented trade payload does **not** include a per-trade sequence/ID. Both adapters therefore preserve `sequence: null` and `sequence_semantics: NOT_DOCUMENTED_BY_VENUE`. They must not be wired into sequence-dependent candle logic until an independently verified identity policy exists. A raw-payload SHA-256 is only a fingerprint for exact-replay diagnostics, not an exchange identity.

The REST endpoint returns a latest-trades window, not a complete event log. The REST collector labels it `LATEST_WINDOW_ONLY`, polls no faster than once per 15 seconds, and never infers that unseen events were absent. This mode can miss trades between polls and is for observation/market-data validation only.

## Safety

- Disabled by default; explicit `enabled=True` is required.
- Public market data only; no API key is accepted or required.
- No account, wallet, order, or withdrawal APIs.
- Append-only JSONL with flush and fsync.
- No Git operations, no pushes, no writes to `main`, no strategy execution.
- Bounded runtime and strict decimal, side, symbol, and timezone validation.
- Socket.IO client is pinned to the Python Socket.IO 4.x family to match Wallex's documented JavaScript Socket.IO v2.x protocol.

## Verified in this change

- Live public REST requests to markets, depth, and recent trades returned HTTP 200 with `success=true`.
- BTCUSDT market metadata was present; depth returned 50 asks and 50 bids; the latest-trades endpoint returned 50 records, all 50 normalized successfully in the bounded check.
- The focused automated suite passed: 21 tests.
- A bounded Socket.IO attempt from the available VPS returned a connection error; therefore the real-time Socket.IO channel is **not yet verified** and must not be described as connected.

## Use

For a bounded REST observation run, instantiate `WallexRestWindowCollectorV1(enabled=True, interval_seconds=15, max_runtime_seconds=60)` in an explicitly supervised test process. For Socket.IO, use `WallexReadOnlyCollectorV1(enabled=True, max_runtime_seconds=60)` only after a bounded live capture confirms subscription and incoming frames. Neither collector can place orders.

## Production acceptance gates

1. CI stays green.
2. Verify Socket.IO protocol compatibility, channel subscription, actual frames, event frequency, and reconnect behavior from the intended runtime network.
3. Compare raw frames with normalized records; verify timestamp freshness and error handling.
4. Confirm downstream ingestion handles unknown sequence semantics without inventing IDs or treating timestamps as sequence.
5. Keep execution disabled until source identity, gap/coverage, and runtime safety gates are independently satisfied.
