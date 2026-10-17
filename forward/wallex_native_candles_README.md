# Wallex Native OHLCV Adapter v1 (isolated / read-only)

## Purpose
forward/wallex_native_candles_v1.py is an isolated read-only client for the documented Wallex public endpoint GET https://api.wallex.ir/v1/udf/history. Official reference: https://api-docs.wallex.ir/ (section “کندل‌ها / آمار OHLC بازارها”).

The adapter accepts symbol, resolution, from, to; preserves numeric precision with Decimal; preserves the source Unix open timestamp; validates response shape, OHLC bounds, resolution alignment, duplicates and ordering; and returns only bars whose full interval has ended by the caller's as_of time. It never manufactures missing bars and never uses account credentials.

Supported resolutions documented by Wallex: 1, 60, 180, 360, 720, 1D. 1 means one minute; 60 means 60 minutes (one hour), not one second.

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

Live smoke evidence (read-only, bounded) is stored under evidence/. Raw HTTP response bytes were hashed and kept on the VPS in /tmp; the repository evidence records the SHA-256 and selected metadata, not a mutable market-data archive.
