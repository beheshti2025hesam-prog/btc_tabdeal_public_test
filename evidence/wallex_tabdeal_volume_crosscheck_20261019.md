# Wallex–Tabdeal volume cross-check (read-only)

Capture date: 2026-10-19 UTC
Scope: public endpoints only; no API keys, account endpoints, writes, deployment, or trading.

## Requests and raw-response fingerprints

| Source | Endpoint | HTTP | Response SHA-256 |
|---|---|---:|---|
| Wallex native candles | `GET https://api.wallex.ir/v1/udf/history?symbol=BTCUSDT&resolution=1&from=1792417020&to=1792424220` | 200 | `a7a11729b5d207b976c301806cacb6295aea356e11615dccf6d617394d3c7104` |
| Tabdeal Spot public trades | `GET https://api1.tabdeal.org/r/api/v1/trades?symbol=BTCUSDT&limit=1000` | 200 | `d25bf88246cabb2a6eb47d11892c6a1f0ab9a6f83fd3e92b514f5609549fcf84` |
| Tabdeal Spot market metadata | `GET https://api1.tabdeal.org/r/api/v1/exchangeInfo?symbol=BTCUSDT` | 200 | `5c55747a6dbaaf9c77f833b14cb72da9cc584f603b5826b0fa3bd958543a204b` |
| Tabdeal server time | `GET https://api1.tabdeal.org/r/api/v1/time` | 200 | `c331b672b1e4abef78d82623ff7c8fa72dbce97e334e61f6533a82f420459c75` |

Wallex returned 120 one-minute candles from 2026-10-19 13:37:00Z through 15:36:00Z. The Tabdeal trades response returned 1,000 rows spanning 2026-10-18 17:57:53.787Z through 2026-10-19 15:34:50.509Z. Tabdeal metadata identified `BTCUSDT` / `BTC_USDT` as Spot `TRADING`.

## Findings

1. **This is not an apples-to-apples candle-volume parity test.** Wallex and Tabdeal are different venues; their market volumes need not be equal. Tabdeal public trades can be aggregated by UTC minute, but an authoritative Tabdeal candle-volume endpoint could not be established from the supplied/current public docs.
2. Read-only probes to four likely Tabdeal kline paths (`/api/v1/klines`, `/r/api/v1/klines`, `/r/fapi/v1/klines`, `/fapi/v1/klines`) returned HTTP 404. Do not treat these guessed paths as supported API contracts; no adapter was added.
3. In the 10-minute UTC window 15:19–15:28 on 2026-10-19, the returned Tabdeal Spot trade sample contained only two trades in the first minute (summed `qty` 0.000947 BTC) and no returned trades in the other nine minutes. Wallex candle `v` for 15:19 was 0.009594 BTC. This single sparse overlap cannot establish a cross-exchange volume ratio or explain Wallex's candle contract.
4. Tabdeal's `quoteQty` field failed the arithmetic check `quoteQty == price * qty` in 968 of 1,000 returned trades (only 32 exact matches). Example row: price 82166.9, qty 0.000023, quoteQty 0.000023; price×qty = 1.8898387. Therefore do not use Tabdeal `quoteQty` as a reliable quote-volume control without further contract evidence. The base-quantity sum used above is `qty`, not `quoteQty`.
5. Tabdeal `serverTime` was 2026-10-19 15:37:27.072Z; host capture time was 15:37:23Z (about +4.072 s). HTTP Date headers were also captured. Use timezone-aware UTC and measured offsets; do not apply Iran/New York fixed offsets.
6. Independent Wallex same-venue reconciliation remains the meaningful volume test: for its latest-trades response (50 rows; 15:19:36Z–15:28:51Z), candle `v` equalled exactly 2× summed trade `quantity` for 7 fully observed minute buckets from 15:20, 15:21, 15:22, 15:24, 15:25, 15:26, and 15:28. The earliest 15:19 bucket was partial (ratio ~4.004), consistent with the trade endpoint's 50-row truncation boundary; do not use that bucket as a complete comparison. This reconfirms the observed Wallex field discrepancy but does not establish its semantic cause.

## Disposition

- Do not divide Wallex `v` by two or normalize it.
- Keep volume-dependent strategy features gated pending an authoritative explanation or independent complete same-venue reconciliation.
- No sequence semantics are needed to build ordinary candles; UTC timestamps remain the alignment key.
- PR #320 remains Draft/unmerged; project status remains `HOLD / NO_TRADE_ONLY`.
- No new adapter, account mutation, collector activation, deployment, or trade was performed.
