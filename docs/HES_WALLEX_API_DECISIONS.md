# HES Trade Agent — Wallex API Evidence & Decisions

Status: documentation-derived; live API behavior and integration are NOT verified by this document.

## Governing decision
Use exchange-provided capabilities first, with minimum complexity. Do not rebuild exchange functionality or impose checks without a demonstrated HES decision/safety requirement.

## Evidence supplied from Wallex documentation by the project owner

### Candles / OHLCV
- Endpoint documented: `GET /v1/udf/history`.
- Query fields shown: `symbol`, `resolution`, `from`, `to` (one supplied page marks them optional; the earlier Swagger excerpt marks them required, so requiredness must be confirmed against the current endpoint contract before implementation).
- Response arrays: `t` (time), `o` (open), `h` (high), `l` (low), `c` (close), `v` (volume), and `s` (status).
- Resolutions listed in the supplied page: `1, 15, 60, 240, 480, 720, 1D, 2D, 3D`.
- Decision: make the exchange's official candles the primary market-data path where consistent with the existing HES design. Do not reconstruct candles from raw trades unless a concrete requirement demonstrates it is necessary.

### Market list
- Endpoint documented: `GET https://api.wallex.com/hector/web/v1/markets`.
- Auth shown: `x-api-key`.
- Response fields shown: `success`, `message`, `result`; internal `result` schema was not visible in the supplied page.
- Decision: use the market-list endpoint only if the existing code needs market metadata; do not assume undocumented fields.

### Market depth
- Endpoint documented: `GET https://api.wallex.com/v1/depth`.
- Query parameter: required `symbol`.
- Auth shown: `x-api-key`.
- Response overview: `result`, `message`, `success`; the earlier supplied basic-services content describes `result.ask` and `result.bid`, each with `price`, `quantity`, `sum`.
- The supplied documentation warns that frequent REST polling may encounter rate limits and points to WebSocket for frequent depth updates.
- Decision: do not poll depth unless HES actually needs it; if frequent updates are needed, assess the exchange-provided WebSocket rather than building a parallel polling system.

### Latest trades
- Endpoint documented: `GET /v1/trades`.
- Query field shown: `symbol` (one page marks optional).
- Fields shown in `result.latestTrades`: `symbol`, `quantity`, `price`, `sum`, `isBuyOrder`, `timestamp`.
- The supplied page warns that frequent REST polling may encounter rate limits and points to a WebSocket feed.
- The supplied REST example/schema does not show a trade ID or sequence number. This means only that the supplied page does not document them; it does NOT prove the exchange lacks such identifiers in other interfaces.
- Decision: latest trades and sequence reconstruction are not prerequisites for the candle path unless the current HES code or strategy has a specific dependency on them.

### Account fees
- Endpoint documented: `GET /v1/account/fee`.
- Example fields: `makerFeeRate`, `takerFeeRate`, `recent_days_sum`.
- Decision: consume only if HES needs account-specific fee inputs for net-profit/risk calculations. Confirm units and interpretation from authoritative current documentation or actual response before relying on them.

## Cross-cutting cautions
- Supplied pages use both `api.wallex.ir` and `api.wallex.com`. Do not silently assume these hosts are interchangeable; use the endpoint's current official base URL and verify the configured environment.
- Examples and schemas are documentation evidence, not proof of live availability, freshness, completeness, or successful authentication.
- Keep requests read-only during initial integration. Never request or store API secrets in chat or commit them to the repository.
- Minimal decision-relevant checks for the candle path: response/schema validity, consistent OHLCV array lengths, valid timestamps and numeric values, sane OHLC relationships, and freshness relative to the strategy's decision horizon. Do not add exhaustive trade sequence validation unless required by an explicit HES dependency.
- Preserve HOLD / NO-TRADE until the existing required gates pass on evidence. This document alone does not pass any runtime gate.

## Implementation workflow
1. Inspect current repository and existing tests before coding; reuse existing components.
2. Map the documented endpoint to the existing market-data adapter and current configuration.
3. Run read-only integration tests using the supported environment; record sanitized response evidence and test results.
4. Add only the smallest necessary changes for demonstrated gaps.
5. Recompute project progress only from verified implementation/test evidence, not from documentation review alone.
