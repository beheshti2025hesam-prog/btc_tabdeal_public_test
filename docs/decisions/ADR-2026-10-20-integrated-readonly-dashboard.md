# ADR — Integrated read-only market dashboard (2026-10-20)

## Status
Accepted for the first UI slice because inspection of the actual HES repository and host found no existing frontend entry point or HES web service. This extends the existing HES Trade Agent repository; it does not create a second trading application.

## Decision
- Add a Python-standard-library dashboard under web/, runnable as a module from the repository.
- Chart candles come from a documented global public market-data endpoint, not the execution venue's chart API. The first provider adapter uses public Binance Spot market data without account credentials.
- Display only validated, fully closed, fresh candles. Preserve source volume exactly; never silently scale or reinterpret it.
- No order controls or submit endpoint. Health/status explicitly report NO_TRADE_ONLY.
- Existing strategy/risk modules remain authoritative. This first UI slice is read-only visualization; it does not claim a trade signal is approved or prove a venue quote executable.
- Bind to 127.0.0.1 by default. Remote exposure requires separately reviewed authentication/reverse-proxy changes.

## Consequences
- The project now has a real UI entry point within the existing repository, without a parallel app or new runtime dependency.
- Venue symbol mapping, venue constraints, spread/slippage, risk approval, idempotent submission and order/fill reconciliation remain mandatory before any concrete execution adapter can be enabled.
- Runtime stays HOLD / NO_TRADE_ONLY. This does not authorize account access, service activation, deployment, or live trading.

## Acceptance
- Unit tests cover candle finality, freshness, OHLC integrity, duplicate timestamps, transport failure and volume preservation.
- Route tests prove dashboard/health behavior and absence of an order route.
- Live public-data smoke testing is separate and never submits orders.
