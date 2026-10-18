# Candle-First: native Wallex OHLCV path v1

## Decision
Candle-based strategies consume official native exchange/broker OHLCV candles where available. They must not require individual-trade sequence identifiers or reconstruct the candle stream from trades. Trade-level sequence/order-flow validation remains a separate capability only for strategies that truly need individual trades.

## Official source
Wallex API documentation describes the public history endpoint:

- `GET https://api.wallex.ir/v1/udf/history`
- Query: `symbol`, `resolution` (minutes), `from`, `to` (Unix seconds)
- Response arrays: `s`, `t`, `o`, `h`, `l`, `c`, `v`

Official docs: https://api-docs.wallex.ir/ and https://developers.wallex.ir/

## Implementation in this PR
- `forward/native_wallex_ohlcv_v1.py` calls the native endpoint read-only and parses OHLCV into immutable candles.
- Decimal values are preserved; source timestamps are UTC-aware; candle finality is derived from candle close time relative to a timezone-aware `as_of`.
- Malformed response status, unequal arrays, non-monotonic/misaligned timestamps, invalid OHLC bounds, invalid numeric values, and naive timestamps fail closed.
- Missing intervals are not fabricated. This adapter has no dependency on trade sequence IDs.
- `tests/test_native_wallex_ohlcv_v1.py` covers parsing, transport URL construction, precision, candle finality, malformed data and ordering.

## Explicit limitations / acceptance gates
- Unit tests and adapter construction do not prove live network access or live endpoint behavior from the authorized runner.
- No raw production response bytes, SHA-256 evidence, official chart comparison, freshness SLA, gap policy approval, or endpoint clock-offset result is claimed by this PR.
- Verify supported symbols/resolutions against the current official API, then run read-only controlled fetch and preserve raw response bytes + SHA-256 + request interval + retrieval timestamp.
- Compare sampled candles against the official Wallex chart for identical symbol/timeframe/timezone and document exact match/tolerance.
- Keep collector activation, deployment and trading disabled until these gates and applicable security checks pass.

## Project disposition
`HOLD / NO_TRADE_ONLY`. This PR establishes an independent native-candle path and tests; it does not authorize live trading or declare end-to-end parity complete.
