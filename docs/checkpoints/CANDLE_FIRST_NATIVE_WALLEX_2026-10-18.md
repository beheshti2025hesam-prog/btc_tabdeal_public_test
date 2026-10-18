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
- `forward/native_wallex_ohlcv_v1.py`: read-only adapter; immutable candles; Decimal precision; UTC-aware times; closed/open status from candle close time; strict OHLCV shape, timestamp, alignment and numeric validation; documented resolution allowlist; bounded retries for temporary network failures and HTTP 408/429/5xx.
- `NativeFetchEvidence` retains exact response bytes, retrieval time, request URL, SHA-256, and HTTP Date / estimated server clock offset when provided.
- `tests/test_native_wallex_ohlcv_v1.py`: deterministic positive/adversarial tests, including bounded retry and failure-injection coverage.
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


## First live read-only evidence — 2026-10-18
- Exact source commit tested: `37e0b5c9211333849a9910f12f1f8f52b96bed08`.
- GitHub Actions run `39143105580`: deterministic suite **26 passed**; live read-only probe **PASS**.
- BTCUSDT/1m returned 9 candles over the requested 10-minute window; no timestamp gaps or duplicates; latest closed candle age was 43.153282 seconds.
- HTTP `Date` header: `Sun, 18 Oct 2026 16:03:43 GMT`; estimated offset against runner retrieval time: `-0.836194s` (within the probe's provisional 5-second smoke threshold).
- Raw response SHA-256: `fd829ff1fab225ce6775151f98da032b8b07503c1acdf40814adfdd873a1b27c`; byte-for-byte verification against the downloaded CI artifact passed.
- Durable evidence is stored in `docs/evidence/wallex-native-ohlcv-2026-10-18.manifest.json` and `docs/evidence/wallex-native-ohlcv-2026-10-18.raw.json`.
- Official frontend asset inspection found `T.f.get("v1/udf/history",{params:e})` in the fetched Wallex frontend bundle, with the production API base `https://api.wallex.ir`. Asset hashes and retrieval metadata are pinned in the evidence manifest.

## Still not authorized / not yet proven
- Exact candle-by-candle parity against the rendered external TradingView chart is **not verified**; the frontend code observation alone is not proof of rendered chart parity.
- Reconnect/retry behavior and production freshness/gap/clock-offset SLAs remain unapproved/unverified.
- No collector activation, deployment, or trading. Maintain `HOLD / NO_TRADE_ONLY`.
