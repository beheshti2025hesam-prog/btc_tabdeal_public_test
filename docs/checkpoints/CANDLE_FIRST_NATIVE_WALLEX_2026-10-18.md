# Candle-First: native Wallex OHLCV path v1

## Decision
Candle-based strategies consume official native exchange/broker OHLCV candles where available. They must not require individual-trade sequence identifiers or reconstruct candles from trades. Trade-level sequence/order-flow validation remains separate for strategies that truly require individual trades.

## Official contract verified from Wallex documentation
- Endpoint: `GET https://api.wallex.ir/v1/udf/history`
- Query: `symbol`, `resolution`, `from`, `to` (Unix timestamps)
- Response arrays: `s`, `t`, `o`, `h`, `l`, `c`, `v`
- Documented minute resolutions: `1`, `60`, `180`, `360`, `720`; documentation also lists `1D`.
- The adapter currently enables only the five documented minute resolutions. The `1D` option is intentionally deferred until daily-boundary/timezone behavior is verified.
- The official market docs use symbols such as `BTCUSDT`; validate requested symbols against the current market list.

Official source: https://api-docs.wallex.ir/ (section “کندل‌ها / OHLC market statistics”).

## Implementation
- `forward/native_wallex_ohlcv_v1.py`: read-only adapter; immutable candles; Decimal precision; UTC-aware times; closed/open status from candle close time; strict OHLCV shape, timestamp, alignment and numeric validation; documented resolution allowlist.
- `NativeFetchEvidence` retains exact response bytes, retrieval time, request URL, SHA-256, and HTTP Date / estimated server clock offset when provided.
- `tests/test_native_wallex_ohlcv_v1.py`: deterministic positive and adversarial tests.
- `scripts/verify_native_wallex_ohlcv.py`: read-only CI probe for BTCUSDT/1m; captures raw bytes + SHA-256 + request/retrieval metadata; checks freshness (<= 300s), gaps, and HTTP Date clock offset (<= 5s).
- `.github/workflows/native-wallex-ohlcv-tests.yml`: runs deterministic tests and the live public-data probe on relevant PR commits, checking out the exact PR head SHA; stores evidence artifact for 90 days.

## Acceptance gates (do not silently mark these passed)
1. Deterministic tests pass on the exact PR head.
2. Live endpoint returns valid data from the authorized CI runner; raw bytes, SHA-256, request interval and retrieval timestamp are preserved.
3. Supported symbol/resolution are confirmed against the current official API; only documented minute resolutions are enabled here.
4. Candle gaps, freshness and server clock offset are measured and policy thresholds approved.
5. Sample candles are compared against the official Wallex chart for the same symbol, interval and UTC timestamps; exact equality/tolerance is documented.
6. Reconnect/retry behavior is covered before any collector uses this adapter.
7. Security and repository identity gates pass.

## Safety
No collector activation, deployment or trading is authorized by this adapter. Project disposition remains `HOLD / NO_TRADE_ONLY`. Native candles remove sequence-ID dependence for candle-only strategies; they do not settle trade-sequence semantics for Order Flow strategies.
