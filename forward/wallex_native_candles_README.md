# Wallex Native OHLCV Adapter v1 (isolated / read-only)

## Purpose
forward/wallex_native_candles_v1.py is an isolated read-only client for the documented Wallex public endpoint GET https://api.wallex.ir/v1/udf/history. Official reference: https://api-docs.wallex.ir/ (section “کندل‌ها / آمار OHLC بازارها”).

The adapter accepts symbol, resolution, from, to; preserves numeric precision with Decimal; preserves the source Unix open timestamp; validates response shape, OHLC bounds, resolution alignment, duplicates and ordering; and returns only bars whose full interval has ended by the caller's as_of time. It never manufactures missing bars and never uses account credentials.

## Empirically verified resolution support
The official API reference lists `1`, `60`, `180`, `360`, `720`, and `1D` as supported resolutions. The inspected official trading UI fallback advertises `1`, `5`, `15`, `30`, `60`, `1D`, `1W`, and `1M`. Bounded direct/no-proxy BTCUSDT probes on 2026-10-17 tested these values across appropriate ranges.

- `1`: returned 1,439 bars with 60-second spacing.
- `60`: returned 24 bars with 3,600-second spacing.
- `1D` and `D`: returned the same one daily bar in this range.
- `15`: returned the same 1-minute payload as `1` (1,439 bars; 60-second spacing). Do not treat it as 15-minute candles.
- `720`: returned the same 1-hour payload as `60` (24 bars; 3,600-second spacing). Do not treat it as 12-hour candles.
- `5`, `30`, `180`, `360`, `1W`, and `1M`: HTTP 200 with source status `error`, no bars.

Therefore the adapter enables only `1` (1-minute), `60` (1-hour), and `1D` (daily). The other resolutions fail closed until verified in a new bounded live probe. This is an empirical observation for the tested request and date, not a permanent exchange guarantee.

## Boundaries / non-claims
- The adapter is not wired into the live collector, strategy, decision runner, or execution path.
- A successful public endpoint response proves reachability and payload validity for that bounded request only.
- No chart parity has been claimed. Compare sampled candles against the exchange UI for matching symbol/timeframe and document timestamp conventions before any downstream use.
- source_observed_at is the local response-receive timestamp; it is not an exchange-generated candle-finalization timestamp.
- A candle is marked closed only by interval end <= as_of. This is a conservative client-side rule, not a claim about Wallex's internal finalization guarantee.
- Native OHLCV has no trade IDs. WebSocket trade frames observed in the smoke test had no unique trade ID/sequence field; event ordering, replay, deduplication, and gap-recovery semantics remain UNKNOWN.
- National-intranet availability is OUT OF SCOPE BY USER DECISION (2026-10-17); it is not a verified capability and is not an acceptance gate. Current specific regulatory authorization remains UNVERIFIED.
- No orders, private endpoints, keys, deployment, collector activation, or trading were used.

## Tests
    python -m pytest -q forward/test_wallex_native_candles_v1.py

Live smoke evidence is stored under evidence/. Raw response payloads are hashed and preserved on the VPS under /srv/hes-evidence/wallex. Chart parity remains unverified.


## Exact raw HTTP response capture (opt-in, v1)
- `fetch_history(..., raw_evidence_path=...)` can preserve the exact response body bytes before JSON parsing in a write-once evidence envelope.
- The envelope records the public request URL/parameters, HTTP status, local receive time, byte count, Base64 body, and SHA-256 over the exact body bytes. Existing target paths are never overwritten; file contents are fsynced before return.
- `verify_raw_http_response_v1(path)` verifies the byte count and raw-body SHA-256, then returns the exact decoded bytes for replay.
- Capture is opt-in and must use a unique evidence path for each response. The default adapter call still does not retain raw response bytes.
- This capability does **not** yet attach raw evidence identity to `HES_WALLEX_CANDLE_OBSERVATION_V1`; therefore end-to-end source-to-feature provenance and replay are not yet accepted. Do not set `raw_source_replay_verified=true` based on this helper alone.

- `replay_raw_http_response_v1(path, as_of=..., expected_candle_records=...)` verifies the envelope and raw body, re-parses the exact body with the same native parser, enforces the requested range, and requires exact candle hashes/fields to match the observation. Its `RAW_REPLAY_VERIFIED` result applies only to that specific evidence file and expected candle set; it does not by itself prove source-to-feature lineage or chart parity.
