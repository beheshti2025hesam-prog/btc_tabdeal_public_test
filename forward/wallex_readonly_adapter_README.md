# Wallex Read-Only Market Data Adapter v1

This adapter is an isolated, read-only integration for Wallex Spot `BTCUSDT`.

## Public contract used

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent trades: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Socket.IO public trade channel: `BTCUSDT@trade`, event `Broadcaster(channel, data)`
- Public trade payload fields: `price`, `quantity`, `isBuyOrder`, `timestamp`

The documented trade payload does **not** include a per-trade sequence/ID. The adapter explicitly emits `sequence: null` and `sequence_semantics: NOT_DOCUMENTED_BY_VENUE`; it must not be wired to sequence-dependent candle logic until an independently verified identity policy exists. A raw-payload SHA-256 is included for exact replay diagnostics, not claimed as exchange identity.

## Safety

- Disabled by default; caller must explicitly pass `enabled=True`.
- Public market data only; no API key is accepted or required.
- No account, wallet, order, or withdrawal APIs.
- Append-only JSONL with flush and fsync.
- No Git operations, no pushes, no writes to `main`, no strategy execution.
- Bounded runtime for each connection attempt.
- Strict channel, decimal, side, and timezone validation.

## Use

Install `requirements.txt`, then instantiate `WallexReadOnlyCollectorV1(enabled=True, max_runtime_seconds=60)` in an explicitly supervised test process. Inspect the emitted JSONL records and feed health before any integration into downstream HES pipelines. This is not an authorization to trade.

## Acceptance gates before production integration

1. Unit tests pass and CI is green.
2. A bounded live capture confirms Socket.IO protocol compatibility, channel subscription, payload shape, and event frequency.
3. Captured raw frames and normalized records are compared; timestamp freshness and disconnect/reconnect behavior are tested.
4. Repeated identical payloads are measured but not deduplicated as trades solely by hash without policy review.
5. Downstream pipeline handles unknown sequence semantics without inventing IDs or treating timestamps as sequence.
6. Runtime is isolated from the legacy collector and has no order-execution permissions.
