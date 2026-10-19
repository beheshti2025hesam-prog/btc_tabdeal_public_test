# Candle-First: native Wallex OHLCV path v1

## Decision
Candle-based strategies consume official native exchange/broker OHLCV candles where available. They must not require individual-trade sequence identifiers or reconstruct candles from trades. Trade-level sequence/order-flow validation remains separate for strategies that truly require individual trades.

## Official contract verified from Wallex documentation
- Endpoint: `GET https://api.wallex.ir/v1/udf/history`
- Query: `symbol`, `resolution`, `from`, `to` (Unix timestamps)
- Response arrays: `s`, `t`, `o`, `h`, `l`, `c`, `v`
- Documented minute resolutions: `1`, `60`, `180`, `360`, `720`; documentation also lists `1D`.
- The adapter currently enables only the two resolutions verified to return matching timestamp spacing. The `1D` option is intentionally deferred until daily-boundary/timezone behavior is verified.
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
5. Candle data parity is verified by comparing raw native UDF candles with trade-derived OHLC on complete same-symbol UTC intervals and by verifying the official chart frontend maps the same UDF fields directly to chart bars. A rendered screenshot is required only for a claim about pixel/rendering parity, not for the native data-path contract.
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
- Pixel-level parity against an independently rendered chart screenshot is **not verified**. This is not a blocker for the native candle data-path contract once raw UDF candles and the official frontend's direct field mapping are verified. Do not claim pixel-level parity.
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


## Live chart/API and resolution review — 2026-10-19
- Read-only live API capture and raw hashes are recorded in [evidence/wallex_chart_volume_live_review_20261019.json](../../evidence/wallex_chart_volume_live_review_20261019.json) and [evidence/wallex_resolution_probe_6h_20261019.json](../../evidence/wallex_resolution_probe_6h_20261019.json); corresponding raw responses are in evidence/raw.
- Live six-hour resolution probe with cache-bypass query and no-cache headers: `1` returned 360 rows at 60-second intervals; `15` returned byte-identical 1-minute data; `60`, `240`, `480`, and `720` returned byte-identical hourly data; `5`, `180`, and `360` returned `Invalid resolution!`. The adapter is therefore restricted to `1` and `60` until other resolutions are shown to honor their requested intervals.
- Live BTCUSDT closed-minute comparisons show matching trade-derived OHLC and UDF OHLC, while UDF `v` remains exactly 2x summed quantities in observed overlapping bars. Earlier evidence remains 99/99 bars across five symbols with the same ratio. Do not divide volume by two or infer units.
- Official Wallex frontend source inspection maps UDF `t/o/h/l/c/v` directly to chart bars. TradingView's BTCUSDT market list did not include Wallex, so its other-exchange volume is not a valid same-market comparator. Independent rendered screenshot parity remains NOT VERIFIED; browser download via Puppeteer was denied (HTTP 403), and external screenshot retrieval timed out.
- Local clean checkout at final evidence-only head `c2f11b3b56fa24e49a7badc83a2cc3327b3960c1`: targeted suite 31 passed; live read-only probe passed. GitHub Actions run [39275572903](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39275572903) has both deterministic-tests and live-read-only-probe successful.
- Disposition remains `HOLD / NO_TRADE_ONLY`; no trading, deployment, or collector activation. Volume semantics and independent rendered chart verification remain blockers.


## Final-head parity and scope correction — 2026-10-19 15:26 UTC

The evidence-bounded scope is now explicit: **native candle data-path parity is separate from rendered-pixel parity and trade-sequence semantics**. Do not expand this task into generic sequence research or build candles from trades.

- Fresh live evidence is in [`evidence/wallex_chart_volume_live_review_20261019_followup.md`](../../evidence/wallex_chart_volume_live_review_20261019_followup.md).
- Across BTCUSDT, ETHUSDT, BTCTMN, ETHTMN and SOLUSDT, 80/80 fully overlapping closed 1-minute bars matched exact OHLC between UDF candles and OHLC reconstructed from the public trade endpoint after sorting by timezone-aware UTC timestamps. No sequence field was used.
- The official Wallex chart page's referenced frontend code maps UDF `t/o/h/l/c/v` directly into chart bars. This and raw API evidence verify the chart's data path. Pixel-level screenshot parity remains unverified and is not required to accept the native data-path adapter.
- UDF `v` was exactly 2x the sum of public trade `quantity` in those same 80 bars. This is a difference between two API fields, not a mismatch between the chart frontend and its UDF candle source. Preserve UDF `v` verbatim for chart parity; do not divide by two. Keep volume-dependent strategy features gated until the field semantics are documented or otherwise independently established.
- UTC is the canonical comparison timeline for both adapters. Iran/New York daylight and standard-time tests pass. Never apply a fixed timezone offset.
- Final reviewed head at this checkpoint: `82c2810054660016bdcaea8625dd5dde213ea89a`; targeted tests 33 passed, full repository tests 474 passed; live read-only probe passed with 10 candles, no gaps, latest closed age 56.75 seconds and estimated HTTP Date offset −0.84 seconds.
- Only live-verified resolutions `1` and `60` are enabled; other resolutions fail closed. Sequence IDs are not used for candle construction or timestamp alignment.
- Status remains `HOLD / NO_TRADE_ONLY` for execution and volume-dependent strategy promotion. This adapter/evidence work does not authorize collector activation, deployment, account changes, or trading.
