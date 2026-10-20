# Wallex chart/API parity follow-up — 2026-10-19

## Scope and method

Read-only live verification from the project VPS. All candle timestamps and trade timestamps were normalized to timezone-aware UTC before comparison. No sequence/id ordering, gap inference, or cross-reconnect semantics were used. No account credentials or trading actions were involved.

Capture time: `2026-10-19T15:26:16.617381Z` for the multi-symbol cross-check; the dedicated live candle health probe completed at `2026-10-19T15:26:56.836417Z`.

## Fresh public endpoint evidence

For each symbol, `GET /v1/trades?symbol=...` was compared against `GET /v1/udf/history?symbol=...&resolution=1&from=...&to=...`. Only complete overlapping closed one-minute bars within the returned trade-time window were compared.

| Symbol | Complete overlapping bars | OHLC exact matches | UDF `v` / sum of public trade `quantity` |
|---|---:|---:|---|
| BTCUSDT | 6 | 6 | 2× on all 6 |
| ETHUSDT | 18 | 18 | 2× on all 18 |
| BTCTMN | 8 | 8 | 2× on all 8 |
| ETHTMN | 20 | 20 | 2× on all 20 |
| SOLUSDT | 28 | 28 | 2× on all 28 |
| **Total** | **80** | **80** | **2× on all 80** |

Raw response SHA-256 values captured in the VPS audit manifest:

| Symbol | `/v1/trades` SHA-256 | `/v1/udf/history` SHA-256 |
|---|---|---|
| BTCUSDT | `779624eacf83c365cdee2622d222ce9f4c0fd426eb3ce3d01ee9275e24bd0383` | `c77fc581f6ceea6d56de0189eb1da5d92c92857e7eb3d0031bbe53b2b3cf4101` |
| ETHUSDT | `91b1120b387937f1b6cb698a93aa10d259fef53f799c3bce9dcdd477a669ca1f` | `f13e9dd89a04cc1789f786c7ea59e078747d70554a8bfd144b42782ac7e2abd4` |
| BTCTMN | `7719281047ab82e29c02ea5ddf480ace6ce940b2eba415cb48b5aea55837934e` | `0cc77c6511fbd8f3a9c1c5669c00115adbbb89b1b515f1714edeb580dac119f1` |
| ETHTMN | `a8a28d9d345dc5ee14f357f2e64c3660d35e164007ff43a9b899d33b9e7b1d4e` | `e85a88042b98c132024e848e29fcb1c3f1f5f0296c5433808748055ecadb0301` |
| SOLUSDT | `538666edf4698ef294a9c6660454cb0caeec1f1d5d77d090db5118cc93410550` | `b5a2169100886d16c4605e129a867655726f5f7a9188fe5bd393529bf9723f13` |

Endpoint roots:
- `https://api.wallex.ir/v1/trades`
- `https://api.wallex.ir/v1/udf/history`

## Official chart data path

Fresh request to `https://wallex.ir/app/trade/BTCUSDT` returned HTTP 200 at `Mon, 19 Oct 2026 15:26:17 GMT`, 694,674 bytes, SHA-256 `1d0b12793246fc622f34473050abf62f56d88e0ac28f9891bb4b273cd124e684`.

A JavaScript chunk referenced by the page, `https://wallex.ir/_next/static/chunks/21v8tx2u_2l_g.js`, SHA-256 `333bac8e5b79e4188dbd764fd4d498940517e0420ced6cacf3f62a90c0f87d82`, contains a UDF `getBars` handler which requests symbol/resolution/from/to and maps `t/o/h/l/c/v) directly to chart bar time/OHLC/volume. This verifies the official frontend's source-level data path. It is **not** an independent rendered-pixel screenshot.

## Current read-only health probe

The adapter's live probe for BTCUSDT/1m returned HTTP 200 and 10 candles for `2026-10-19T15:16:56.749430Z`–`2026-10-19T15:26:56.749430Z`. Candle opens ran from `15:17:00Z` through `15:26:00Z`, with no gaps. Latest closed candle age was 56.75 seconds. HTTP Date offset estimate was −0.84 seconds, within the probe's 5-second limit. Raw response SHA-256: `10860f1ba58a7f1a48c103b8b20b8ce402df52528f5b405e602732da1ef26864`.

## Resolution guard

The earlier uncached live probe established only `1` and `60` return the requested minute/hour interval correctly. `15` returned one-minute spacing; `240/480/720` returned hourly spacing; `5/180/360` returned `Invalid resolution!`. The adapter must fail closed for all unverified intervals—never silently remap them.

## Timezone invariant

Canonical comparison time is UTC. The Tabdeal adapter's timezone-aware trade timestamp and Wallex candle Unix timestamp were regression-tested against the same instant for both US daylight and standard time:
- 2026-10-19 15:00 UTC = Tehran 18:30 (+03:30) = New York 11:00 (−04:00), local-label difference 450 minutes.
- 2026-01-19 15:00 UTC = Tehran 18:30 (+03:30) = New York 10:00 (−05:00), local-label difference 510 minutes.

Do not apply a fixed Iran–US offset to source timestamps. Local timezone conversion is display-only. No sequence IDs are needed to align ordinary OHLC candles.

## Decision

- **OHLC/time parity:** PASS for the 80 overlapping bars above, and official frontend source maps the native UDF response fields into chart bars.
- **Freshness/gaps:** PASS for the captured BTCUSDT/1m probe only; this is not a universal SLA.
- **Volume semantics:** STILL UNRESOLVED. The exact 2× relation repeats in all 80 freshly checked bars. Do not halve or otherwise transform volume without evidence. For chart parity, use Wallex's native candle `v` exactly as returned; keep volume-dependent strategy/feature promotion gated until its meaning is established.
- **Rendered screenshot:** NOT independently verified in this runner.
- **Safety:** PR #320 remains Draft/unmerged and project disposition remains `HOLD / NO_TRADE_ONLY`. No deployment, collector activation, account mutation, or trading occurred.

This is evidence of observed responses at the capture time, not a claim about undocumented exchange semantics.