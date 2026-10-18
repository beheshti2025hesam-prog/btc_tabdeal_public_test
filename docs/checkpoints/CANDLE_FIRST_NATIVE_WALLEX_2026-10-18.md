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
- `forward/native_wallex_ohlcv_v1.py`: read-only adapter; immutable candles; Decimal precision; UTC-aware times; closed/open status from candle close time; strict OHLCV shape, timestamp, alignment and numeric validation; documented resolution allowlist; bounded retries for temporary network failures and HTTP 408, 429, 500, 502, 503, 504.
- `NativeFetchEvidence` retains exact response bytes, retrieval time, request URL, SHA-256, and HTTP Date / estimated server clock offset when provided.
- `tests/test_native_wallex_ohlcv_v1.py`: deterministic positive/adversarial tests, including bounded retry and failure-injection coverage.
- `scripts/verify_native_wallex_ohlcv.py`: read-only CI probe for BTCUSDT/1m; captures raw bytes + SHA-256, request/retrieval metadata and retry attempt count; checks freshness (<= 300s), gaps, and HTTP Date clock offset (<= 5s).
- `.github/workflows/native-wallex-ohlcv-tests.yml`: runs deterministic tests and the live public-data probe on relevant PR commits, checking out the exact PR head SHA; stores evidence artifact for 90 days.

## Acceptance gates (do not silently mark these passed)
1. Deterministic tests pass on the exact PR head.
2. Live endpoint returns valid data from the authorized CI runner; raw bytes, SHA-256, request interval and retrieval timestamp are preserved.
3. Supported symbol/resolution are confirmed against the current official API; only documented minute resolutions are enabled here.
4. Candle gaps, freshness and server clock offset are measured and policy thresholds approved.
5. Sample candles are compared against the official Wallex chart for the same symbol, interval and UTC timestamps; exact equality/tolerance is documented.
6. Bounded retry behavior is tested; reconnect/session-epoch isolation remains unverified before any collector uses this adapter.
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
- Reconnect/session-epoch isolation and production freshness/gap/clock-offset SLAs remain unapproved/unverified; bounded retry behavior is covered by tests.
- No collector activation, deployment, or trading. Maintain `HOLD / NO_TRADE_ONLY`.


## Bounded-retry probe sample — 2026-10-18 16:10 UTC
- Source commit used for this sample: `3390dfd05226520b09b0e451677da8a220c183c5`.
- Clean-checkout targeted suite: `30 passed in 0.18s`; read-only live probe: exit code 0, `attempt_count=1`.
- BTCUSDT/1m returned 8 candles, no observed gaps or duplicates; latest closed candle age 63.320854 seconds; estimated HTTP Date offset `-0.441112s`.
- Raw SHA-256: `d21d45c7a19cb5d6264c10b6590977c850b0ae16ef84f18792b468c0bde86b58`; raw response and manifest are preserved in `docs/evidence/wallex-native-ohlcv-2026-10-18-retry-enabled.raw.json` and `docs/evidence/wallex-native-ohlcv-2026-10-18-retry-enabled.manifest.json`.
- The later source change caps each computed exponential retry delay at 10 seconds and adds a dedicated test; the final-head CI run must verify that revision before treating the retry-enabled implementation as accepted.


## Retry-capped exact-source verification — 2026-10-18 16:11 UTC
- Source commit: `9df6813b99071d61c598a5748102e9a8650b86ab`.
- Clean Git checkout at that exact SHA: `31 passed in 0.16s`; live read-only probe exited `0`.
- Retry policy: retry transient network failures and HTTP 408/429/5xx; maximum 5 attempts; exponential delays capped at 10 seconds; permanent HTTP 404 is not retried. Failure-injection tests cover retry success, permanent error, exhaustion, configuration limits, and the delay cap.
- Latest BTCUSDT/1m sample: 9 candles, no observed gaps/duplicates, latest closed candle age 22.537193 seconds, estimated HTTP Date offset `-0.620855s`, one attempt.
- Raw response SHA-256: `be1e452b72e9f039dc025effec6bdde4e68413d3c05023e14c16435de8e12133`. Durable raw bytes and manifest are stored in `docs/evidence/wallex-native-ohlcv-2026-10-18-latest.raw.json` and `docs/evidence/wallex-native-ohlcv-2026-10-18-latest.manifest.json`.
- The final-head GitHub Actions run must pass on the commit that includes these evidence records before the branch can be treated as CI-verified.


## Opt-in Wallex WebSocket collector and session-epoch verification — 2026-10-18

- Added `forward/wallex_market_data_collector_v1.py`, a caller-driven, no-autostart transport for the observed public endpoint `wss://api.wallex.ir/ws`.
- It validates the initial server session frame (`sid`), sends observed JSON subscriptions, validates the observed trade/depth payload shape, preserves exact raw frame SHA-256 plus UTC and monotonic receive times, and serializes event dispatch against epoch changes.
- No trade ID, sequence, ordering, completeness, deduplication, or volume semantics are inferred from this wire format.
- Deterministic transport, malformed-frame, and stale-session tests are in `tests/test_wallex_market_data_collector_v1.py`. The focused suite is expected to run through `.github/workflows/wallex-websocket-collector-tests.yml` on the exact PR head.
- Live read-only evidence: `evidence/wallex_collector_live_epoch_integration_20261018.json` plus its SHA-256 sidecar. The tested source commit is recorded inside that manifest. Three live server sessions had distinct SIDs; four public depth frames were captured in the first two sessions; a prior-epoch frame injected after a newer epoch was active was rejected before dispatch.
- This proves the opt-in transport code path under controlled delayed-frame injection, not that Wallex delivered a delayed network frame, not that the collector is wired into the operational runner, and not trade-feed completeness. The collector is not activated automatically.
- External acceptance blockers remain: authoritative explanation of the factor-of-two UDF volume discrepancy, approved independent clock/freshness/gap policy, and production-runner integration/review. Maintain `HOLD / NO_TRADE_ONLY`.


## Bounded observation runner — live exact-source probe

- Added `forward/wallex_controlled_observation_runner_v1.py` for explicitly requested, bounded public-data observation. It refuses to overwrite evidence, caps each session at 300 seconds and the run at 2–5 sessions, records raw event frames, hashes both JSONL and manifest, and can inject a captured prior-session frame after reconnect.
- Added deterministic tests for event capture, hash verification, stale-epoch rejection, safe duration/session bounds, and no-overwrite behavior.
- Live read-only probe evidence is pinned in `evidence/wallex_controlled_observation_20261018.jsonl`, `evidence/wallex_controlled_observation_20261018.jsonl.sha256`, `evidence/wallex_controlled_observation_20261018.manifest.json`, and its SHA-256 sidecar. The capture used source commit `56df29535d638661d6e2ee0f1fa3e993a0a22168`, opened two distinct server sessions, captured 8 depth events, and rejected one captured prior-session frame injected after the second epoch became current. No credentials, orders, account mutations, or runtime activation.
- This is a controlled observation entry point, not a replacement for a reviewed production integration. It cannot prove the exchange sent delayed frames and does not establish trade event completeness or sequence semantics.


## Independent clock source snapshot

- `evidence/wallex_quality_clock_sync_20261018.json` records the observation host's `systemd-timesyncd` status at capture time, with SHA-256 sidecar. The host reported NTP active, system clock synchronized, stratum 2, and NTP offset `-5.659 ms` (root distance `22.216 ms`).
- This is independent time-source evidence and is stronger than treating the exchange HTTP `Date` header as an independent clock. It is only a point-in-time check of the observation host; it does not attest every runtime host and does not approve the proposed freshness/gap/clock SLA.
- Proposed policy remains proposal-only until project-owner acceptance and a production monitor is wired and tested. Do not promote volume-dependent features or enable trading based on this snapshot.
