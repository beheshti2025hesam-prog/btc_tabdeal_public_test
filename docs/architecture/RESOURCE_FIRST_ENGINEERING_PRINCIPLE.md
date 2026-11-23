# HES Trade Agent — Resource-First Engineering Principle

**Status:** Canonical project principle / roadmap constraint  
**Adopted:** 2026-10-18  
**Applies to:** Project DNA, architecture, roadmap, implementation reviews, data pipelines, analytics, and operational tooling.

## Core rule: use the wheel before reinventing it

HES should intelligently reuse, validate, configure, and improve reliable capabilities that already exist in exchanges, brokers, exchanges' charting services, market-data providers, and established libraries. If a suitable native candle/chart/indicator/API capability already exists, do not rebuild it from raw trade sequences merely because we can. Prefer a small, well-tested integration or customization layer over a second implementation of the same capability.

In plain language: **when the wheel already exists, do not reinvent it; use it wisely and make it work better for HES.**

## Practical rules

1. **Native data first.** For candle-based strategies, prefer the relevant venue/provider's official native OHLCV/Kline/candle feed and, where applicable, its documented chart-data interface. Preserve venue, market/product, symbol, timeframe, timestamps, and source provenance.
2. **No unnecessary candle reconstruction.** Do not build candles from individual trade streams or make candle strategies depend on trade sequence IDs when native candles meet the actual requirements. Sequence/order-flow processing remains a separate capability only for features that genuinely need individual-trade granularity or ordering.
3. **Reuse before custom-build.** Before writing a new subsystem, inspect existing venue APIs, broker/platform capabilities, supported indicators, trusted libraries, and current HES code. Choose the smallest reliable adapter/configuration/customization that meets verified requirements.
4. **Customize at the edge.** Add only the thin code needed for normalization, configuration, extra indicators/features, cross-source comparison, validation, provenance, caching, or integration with HES. Avoid copying/reimplementing an entire charting or indicator engine without a demonstrated requirement.
5. **Do not blindly trust providers.** Native does not mean automatically correct or fit for purpose. Verify documented semantics, market/symbol scope, timeframe boundaries, timezone, closed-candle finality, freshness, gaps, duplicates, revisions, outages, reconnect behavior, precision, and parity with the authoritative chart/API when relevant.
6. **Respect terms and operational limits.** Use authorized/public or properly credentialed interfaces, comply with venue/platform terms, rate limits, licensing, privacy, and security requirements. Never scrape or bypass controls when a supported interface exists.
7. **Fallback only for a reason.** If a native capability is unavailable, incomplete, inaccessible, too slow, unsuitable, or fails its acceptance tests, document the gap and compare alternatives. Build a custom replacement only when evidence shows it is necessary; specify its semantics and tests explicitly.
8. **Keep sources and consumers decoupled.** Use versioned adapters/contracts so venue-specific schemas can feed a stable HES interface. Do not force incompatible symbols, timeframes, schemas, or semantics into a legacy consumer; do not fabricate missing candles, timestamps, or sequence IDs.
9. **Keep evidence and safety gates.** Record the source, retrieval time, raw evidence/hash where available, transformations, and exact code/test revision. A reused provider feature still requires tests. Uncertain or invalid inputs must fail closed for the affected decision path.
10. **Spend effort where it creates an advantage.** HES's value should come from smarter evidence combination, context, custom research, risk controls, evaluation, and efficient orchestration—not rebuilding standard market infrastructure without a clear payoff.

## Required implementation workflow

Before implementing a capability:
- Identify what the venue/platform already provides and read its official documentation.
- Compare native capability vs. a thin adapter vs. a custom implementation against explicit needs, reliability, cost, latency, maintenance, and legal/operational constraints.
- Select the least complex option that passes requirements.
- Add only necessary HES-specific customization and adversarial tests.
- Document the decision and remaining gaps; do not claim equivalence until it is measured.

## Current application: Candle-First

For candle-based HES strategies, prefer the active venue's official native candles; currently the project has selected Wallex as its active venue. Do not reopen the settled candle-first decision or return to building candles from trade sequence as a default. Keep Binance Spot/Futures or other venues as comparison/research sources only where the roadmap calls for them, not as an automatic primary-source substitution.

The current Wallex Candle-First implementation still has its own evidence-based acceptance gates, including exact rendered-chart parity, exact-head CI, reconnect/session isolation, and production data-quality/SLA approval. This principle does not mark those gates as passed.

## Safety and governance

- GitHub is the technical source of truth; Memory is the project map/DNA; Notion is the operational roadmap/checkpoint; Chat is the discussion log.
- Preserve Forward-Only and the existing Evidence/Risk gates.
- Current disposition remains **HOLD / NO-TRADE_ONLY** until the relevant acceptance gates pass. This principle authorizes reuse-oriented engineering, not live collection, deployment, or trading.
