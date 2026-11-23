# Wallex Read-Only Market Data Adapters v1

Isolated, read-only integration for Wallex Spot market data.

## Official public endpoints and protocol

- REST market metadata: `GET https://api.wallex.ir/v1/markets`
- REST depth snapshot: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`
- REST recent-trade window: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`
- Official raw WebSocket: `wss://api.wallex.ir/ws`
- Subscribe immediately after socket open: `["subscribe", {"channel":"SYMBOL@trade"}]`
- Trade frame: `["SYMBOL@trade", {"isBuyOrder": true, "price": "...", "quantity": "...", "timestamp": "..."}]`

The official developer example uses the browser's raw `WebSocket` API, sends the JSON subscription on `open`, and receives a JSON-array trade frame. The collector follows this protocol; it does not use a Socket.IO client or wait for an undocumented subscription acknowledgement. The server may send a session/heartbeat JSON object first; it is not a trade event.

## Sequence and coverage contract

The documented trade payload does **not** include a per-trade sequence/ID. The adapter preserves `sequence: null` and `sequence_semantics: NOT_DOCUMENTED_BY_VENUE`. A raw-payload SHA-256 is only a fingerprint for exact-replay diagnostics, not an exchange identity. Do not treat it as proof of unique trades, event order, gap-free delivery, replay, or completeness.

The REST endpoint returns a latest-trades window, not a complete event log. The REST collector labels it `LATEST_WINDOW_ONLY`, polls no faster than once per 15 seconds, and never infers that unseen events were absent. This mode can miss trades between polls and is for observation/market-data validation only.

## Runtime behavior and safety

- Disabled by default; explicit `enabled=True` is required.
- Public market data only; no API key is accepted or required.
- No account, wallet, order, or withdrawal APIs.
- Append-only JSONL with flush and fsync.
- Bounded runtime and strict decimal/symbol/timezone validation.
- A session that receives no valid trade events fails closed rather than returning a success-shaped result.
- Transport reconnection does not prove trade replay or gap recovery; unknown sequence semantics remain a hard gate.
- No Git operations, no pushes from the collector, no writes to `main`, no strategy execution.

## Live verification evidence (2026-10-17)

- Direct/no-proxy REST markets, depth, latest-trades and native candle probes returned HTTP 200 during bounded checks.
- The official trading page's inspected bundle uses a TradingView-compatible datafeed that calls `v1/udf/history`. Live resolution probes found `15` returning 1-minute bars and `720` returning 1-hour bars; the OHLCV adapter now allows only empirically verified `1`, `60`, and `1D`. See `evidence/wallex_timeframe_semantics_2026-10-17.json`.
- One immediate-subscribe raw-WebSocket session received four fresh BTCUSDT trade frames. Subsequent short reconnect probes connected but received no trade frames while REST latest-trade timestamps advanced. This inconsistency means live WebSocket delivery and reconnect reliability remain **UNVERIFIED**; the collector now fails closed if a bounded session is silent.
- No unique trade ID/sequence was observed. Event ordering, replay, gap recovery, and completeness remain UNKNOWN.
- No credentials, orders, production collector activation, deployment, or trading were used.

## Tests

```bash
python -m pytest -q tests/test_wallex_readonly_adapter_v1.py tests/test_wallex_rest_readonly_v1.py
```

## Production acceptance gates

1. Focused CI is green on the final exact commit.
2. Capture repeatable fresh `BTCUSDT@trade` frames from the intended runtime network across multiple sessions.
3. Verify feed freshness and durable JSONL persistence through process restart; treat silence as failure.
4. Establish a venue-supported identity/coverage policy or keep sequence-dependent use blocked.
5. Compare closed candles against the rendered official chart; endpoint-path inspection alone is not visual parity.
6. Keep the collector disabled and execution off until independent source, coverage, recovery and runtime safety gates pass.
