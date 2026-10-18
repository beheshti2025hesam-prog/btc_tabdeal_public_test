# HES Trade Agent — Wallex API Evidence & Decisions

Status: documentation and repository evidence reviewed on 2026-10-18; live API behavior is only verified where pinned read-only evidence explicitly says so. This document does not authorize runtime integration or trading.

## Governing decision
Use exchange-provided capabilities first, with minimum complexity. Do not rebuild exchange functionality or impose checks without a demonstrated HES decision/safety requirement.

## Current official base URL and documented contracts

The current official Wallex API reference states that API endpoints are available through `https://api.wallex.ir`. The newer developer documentation says the same. Therefore, use `api.wallex.ir` as the documented canonical base for new requests, while retaining the older `api.wallex.com` references below as a recorded documentation discrepancy—not as an approved operational alternative.

Sources:
- Official API reference: https://api-docs.wallex.ir/
- Official developer documentation: https://developers.wallex.ir/intro
- Market-list example on the developer documentation: https://developers.wallex.ir/

### Candles / OHLCV
- Endpoint: `GET https://api.wallex.ir/v1/udf/history`.
- Required query fields in the current official API reference: `symbol`, `resolution`, `from`, `to`; timestamps are Unix seconds.
- Response fields: `s`, `t`, `o`, `h`, `l`, `c`, `v`.
- Current official reference lists minute resolutions `1`, `60`, `180`, `360`, `720` and daily `1D`. The current adapter deliberately enables only the five minute resolutions; daily boundary/timezone behavior remains deferred.
- An older supplied documentation excerpt listed a different set (`15`, `240`, `480`, `2D`, `3D`) and marked some query fields optional. This conflicts with the current official reference and is retained as historical discrepancy only. Do not enable these additional resolutions without confirming the current contract.
- Decision: use native exchange candles as the primary path where consistent with HES architecture. Do not reconstruct candles from trades unless a concrete requirement demonstrates it is necessary.

### Market list
- Current official API reference documents `GET https://api.wallex.ir/v1/markets`.
- The developer documentation also shows `GET https://api.wallex.ir/hector/web/v1/markets` as a market-list example. Treat these as distinct documented paths; use the exact path needed by the existing consumer and verify its response schema before depending on it.
- A previously supplied page cited `https://api.wallex.com/hector/web/v1/markets`. This host conflicts with the current official documentation's canonical base URL. Do not use the `.com` host unless Wallex explicitly confirms it.
- Use the market-list endpoint only when the code needs market metadata; validate requested symbols against its actual current response.

### Market depth
- Endpoint: `GET https://api.wallex.ir/v1/depth?symbol=BTCUSDT`.
- The documented response includes `result.ask` and `result.bid` levels with `price`, `quantity`, and `sum`.
- A previously supplied page cited `https://api.wallex.com/v1/depth`; this is a recorded host discrepancy, not an approved alternative.
- The official docs caution against frequent REST polling and point to WebSocket for frequent updates.
- Decision: do not poll depth unless HES actually needs it. If frequent updates are required, assess the documented Socket.IO interface rather than creating a parallel polling system.

### Latest trades
- Endpoint: `GET https://api.wallex.ir/v1/trades?symbol=BTCUSDT`; the current official reference marks `symbol` as required.
- Documented fields include `symbol`, `quantity`, `price`, `sum`, `isBuyOrder`, and `timestamp`.
- The public REST example does not document a trade ID or sequence number. This does not prove such identifiers are absent from every interface.
- The official docs warn that frequent REST polling may encounter rate limits and point to a WebSocket feed.
- Decision: latest trades and sequence reconstruction are not prerequisites for the candle path unless the current HES code or strategy has a specific dependency on them.

### Socket.IO and observed raw WebSocket
- Official documentation demonstrates Socket.IO usage against `https://api.wallex.ir`, with `subscribe` and `Broadcaster` events.
- Pinned read-only evidence on 2026-10-18 records HTTP 503 for both documented Engine.IO polling handshake URLs from the observation host. This means live reachability was not verified from that host/time; it does not establish a global outage.
- The raw `wss://api.wallex.ir/ws` route is a separate observed protocol. Do not treat it as interchangeable with the documented Socket.IO contract without successful verification or written Wallex confirmation.
- Trade identity/order/contiguity and depth snapshot/delta semantics remain unknown unless supported by new authoritative evidence.

### Account fees
- Endpoint: `GET https://api.wallex.ir/v1/account/fee`.
- Example fields include `makerFeeRate`, `takerFeeRate`, and `recent_days_sum`.
- Consume only if HES needs account-specific fee inputs for net-profit/risk calculations. Confirm units and interpretation from authoritative current documentation or an actual response before relying on them.

## Known unresolved semantic discrepancy: candle volume
Pinned read-only evidence recorded exact numeric OHLC agreement between sampled closed candles and public-trade aggregates, while UDF `v` was exactly 2x the summed public `/v1/trades.quantity` in 99 covered bars across five symbols. The reason is not established.
- Preserve the source `v` exactly.
- Do not halve, normalize, or use it to promote volume-dependent features until Wallex provides authoritative semantics and replay evidence supports the interpretation.
- Candle-only OHLC use does not require trade-sequence reconstruction; volume-dependent use remains blocked by this discrepancy.

## Cross-cutting safety rules
- Do not silently treat `api.wallex.ir` and `api.wallex.com` as interchangeable. Current official documentation supports `api.wallex.ir`; the older `.com` references are preserved only as a discrepancy record.
- Documentation/examples are not proof of live availability, freshness, completeness, authentication success, or operational SLA.
- Keep initial integration read-only. Never request or store API secrets in chat or commit them to the repository.
- Validate only decision-relevant integrity: response schema, equal OHLCV array lengths, timestamp validity/alignment, numeric values, OHLC relationships, freshness and failure behavior.
- Do not require exhaustive trade-sequence validation for candle-only strategies absent an explicit dependency.
- Preserve `HOLD / NO-TRADE` until the actual required gates pass on evidence. This document alone does not pass any runtime gate.

## Implementation workflow
1. Inspect the current repository and existing tests before coding; reuse existing components.
2. Map each endpoint to the existing adapter and configuration; avoid the older `.com` host unless officially confirmed.
3. Run read-only integration tests in the supported environment and preserve sanitized raw evidence plus SHA-256.
4. Add only the smallest change needed for a demonstrated gap.
5. Verify the exact commit and its CI results; do not infer acceptance from another commit's green checks.
6. Recompute project progress only from verified implementation/test evidence, not from documentation review alone.
