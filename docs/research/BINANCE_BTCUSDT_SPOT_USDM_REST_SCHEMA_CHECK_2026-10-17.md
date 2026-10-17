# Binance BTCUSDT Spot vs USDⓈ-M Futures — REST Schema Check

- **Capture date:** 2026-10-17 (UTC; observed event/server timestamps below)
- **Purpose:** preliminary read-only schema/identifier check for HES adapter research
- **Scope:** public REST exchange metadata, recent trades, and depth snapshots
- **Not covered:** WebSocket capture, reconnect/replay guarantees, cross-session identity, or live execution
- **Safety:** research only; no account endpoints, credentials, or orders used

## Evidence captured

Read-only Binance connector calls returned the following fields for `BTCUSDT`.

| Market / response | Observed structure | Sample evidence |
|---|---|---|
| Spot exchange metadata | `serverTime`, `symbols[].symbol/status/baseAsset/quoteAsset/filters` | `BTCUSDT`, `TRADING`, base `BTC`, quote `USDT`; `serverTime=1792254761143` |
| Spot recent trades | `id, price, qty, quoteQty, time, isBuyerMaker, isBestMatch` | Five sample IDs: `6770866035…6770866039`; times were Unix milliseconds around `1792254760209–1792254760999` |
| Spot depth snapshot | `lastUpdateId, bids, asks` | `lastUpdateId=101566521923`; bid/ask levels are price/quantity string pairs |
| USDⓈ-M exchange metadata | `serverTime, futuresType, symbols[].symbol/pair/contractType/status/marginAsset/filters` | `BTCUSDT`, `PERPETUAL`, `TRADING`, `marginAsset=USDT`; returned `serverTime=1792137674765` |
| USDⓈ-M recent trades | `id, price, qty, quoteQty, time, isBuyerMaker, isRPITrade` | Five sample IDs: `8181655228…8181655232`; times were Unix milliseconds around `1792254760702–1792254761275` |
| USDⓈ-M depth snapshot | `lastUpdateId, E, T, bids, asks` | `lastUpdateId=11846095418970`; `E=1792254759158`, `T=1792254759153` |

## Conservative interpretation

1. Spot trade `id` and USDⓈ-M trade `id` are distinct market-specific fields in different response schemas. Do **not** compare their numeric values across products or use them as book update sequence numbers.
2. The five returned trade IDs in each sample were consecutive within that small REST response. This observation is **not proof** of universal contiguity, complete delivery, or continuity across reconnects.
3. Spot and USDⓈ-M depth snapshots expose `lastUpdateId`. A snapshot by itself does not prove the WebSocket diff-depth contract; sequence-range fields and the official snapshot-bridging procedure must be checked separately for each product.
4. The USDⓈ-M exchange metadata `serverTime` value was materially older than timestamps in the contemporaneous returned trades/depth response. Treat this as a freshness discrepancy in the captured connector responses; do not use that metadata timestamp as the capture clock without a fresh independent check.
5. This is a REST schema observation only. It does not verify WebSocket message shapes, gap recovery, replay policy, duplicate handling, or cross-reconnect semantics.

## Official public API references for independent reproduction

- Spot exchange metadata: https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT
- Spot recent trades: https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=5
- Spot depth snapshot: https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=5
- USDⓈ-M exchange metadata: https://fapi.binance.com/fapi/v1/exchangeInfo
- USDⓈ-M recent trades: https://fapi.binance.com/fapi/v1/trades?symbol=BTCUSDT&limit=5
- USDⓈ-M depth snapshot: https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=5


## WebSocket verification plan (not yet executed)

Official documentation entry points for the next review:

- Spot WebSocket streams: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- USDⓈ-M Futures WebSocket market streams: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams

Capture requirements before enabling any adapter capability:

1. Save unmodified raw frames with local receive time, connection/session identifier, endpoint, subscription request, and a SHA-256 digest per frame or capture file.
2. For Spot diff-depth, record the event update range `U` to `u` and bridge the initial REST snapshot using the documented `lastUpdateId` procedure. If a range indicates a gap, discard the local book and resynchronize; never silently continue.
3. For USDⓈ-M diff-depth, record `U`, `u`, and `pu`; verify continuity using the official procedure for that stream. A REST snapshot's `lastUpdateId` alone is not evidence of a complete WebSocket book.
4. For trade streams, preserve the exact product-specific event schema and trade identifiers. Do not conflate Spot trade IDs, Futures trade IDs, aggregate-trade IDs, and depth update IDs.
5. Force a controlled disconnect/reconnect and compare captured events only where the official protocol provides a documented recovery mechanism. Do not infer guaranteed replay or completeness merely because IDs look consecutive.
6. Have a second reviewer independently reproduce the capture and validate the raw evidence hashes before marking this research gate complete.

**Current gate:** OPEN — this plan is a test specification, not evidence that WebSocket capture, reconnect recovery, or independent review has passed.

## Next evidence gate

Retrieve the official Spot and USDⓈ-M WebSocket documentation and capture raw messages for trade and diff-depth channels. Verify fields, timestamps, update ranges, and reconnect behavior separately. Until those checks are committed and tested, no WebSocket continuity guarantee should be added to the HES adapter registry.

## Official WebSocket documentation cross-check (2026-10-17)

The official documentation pages were opened and their current schema sections inspected. This is **documentation verification only**; no live WebSocket frame capture or reconnect experiment has been performed.

| Product / stream | Documented fields relevant to identity or ordering | Safe conclusion |
|---|---|---|
| Spot raw trade `<symbol>@trade` | `t` trade ID; `E` event time; `T` trade time | `t` is a trade identifier in this stream, not an order-book update sequence. Do not compare it to `U/u` or Futures IDs. |
| Spot aggregate trade `<symbol>@aggTrade` | `a` aggregate trade ID; `f/l` first/last raw trade IDs; `E/T` timestamps | These identifiers describe aggregate-trade records and their underlying trade range; they are not interchangeable with raw trade `t` or depth update IDs. |
| Spot diff-depth `<symbol>@depth` | `U` first update ID; `u` final update ID; REST snapshot `lastUpdateId` | The official snapshot-bridging and gap-reset procedure applies to this specific Spot book stream. A gap invalidates the local book and requires a fresh snapshot/bootstrap. |
| USDⓈ-M Futures diff-depth `<symbol>@depth@<speed>` | `U` first update ID; `u` final update ID; `pu` final update ID of the previous stream event; `E/T` timestamps | Preserve and validate the Futures-specific linkage; do not substitute the Spot-only procedure for the documented `pu` relationship. |
| USDⓈ-M Futures post-migration book payloads | Documentation says payloads may include `ps` (pair symbol) and `st` (symbol type: 1=UM, 2=CM) | Capture and validate these fields where present; never silently merge UM and CM records solely because their visible symbol/pair strings resemble one another. |

Official sources checked:
- Spot WebSocket streams: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- USDⓈ-M Futures WebSocket market streams: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams

### Updated next-step gate

1. Capture raw Spot `trade`, `aggTrade`, and `depth` frames, plus USDⓈ-M Futures `aggTrade` and diff-depth frames, with endpoint/stream name, subscription request, connection/session ID, receive timestamps, and raw SHA-256.
2. For Spot depth, reproduce the documented REST snapshot bridge and deliberate gap-triggered resync.
3. For USDⓈ-M depth, validate the `U/u/pu` sequence relationship against the official procedure and force a controlled reconnect.
4. Keep Spot trade `t`, Spot aggregate `a/f/l`, Futures aggregate IDs, and depth update IDs in separate typed fields.
5. Commit capture files plus a manifest and have an independent reviewer recompute hashes.

**Gate remains OPEN:** the schema cross-check is now documented, but live capture, gap/reconnect tests, hash reproduction, and independent review are still outstanding. No adapter capability is promoted by this documentation update.
