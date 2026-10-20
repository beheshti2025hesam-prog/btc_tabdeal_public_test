# HES Trade Agent — Roadmap: Independent Market Intelligence and Venue Execution

**Decision recorded:** 2026-10-20. This is an architecture/roadmap decision, not a claim that all components are implemented or production-ready.

## Target flow
`Documented market-data/chart feeds + approved news/context` → `validated canonical market-data layer` → `strategy and risk engine` → `signal, entry, SL, TP, sizing and limits` → `venue-specific private API adapter` → `order/fill reconciliation and execution safety`.

## Workstreams
1. **Market-data:** prioritize TradingView or a comparable global chart/data-source integration. Store provider, venue/instrument, timeframe, timestamp, units and data-quality metadata. Verify symbol/time mapping and candle parity; do not assume one feed equals every venue's executable price.
2. **Strategy/risk:** use validated candles and selected news/context. Produce proposals only after strategy and risk checks. Entry/SL/TP are not guarantees of execution or profit.
3. **Sequence independence:** ordinary candle construction and candle-based analysis do not depend on undocumented sequence IDs. Sequence/order-book semantics are required only for a specific feature that demonstrably needs a stateful book and has a documented adapter contract.
4. **Volume independence:** preserve source volume as provided and mark unexplained semantics unknown. The core candle pipeline proceeds; volume-dependent features stay disabled until meaning/units are established.
5. **Exchange support:** routine support emails/replies are not a dependency. Contact support only if a safety-critical venue capability is essential and cannot be established from public docs plus reproducible evidence. Unknown means unknown—never guess.
6. **Execution adapters:** private APIs submit and reconcile venue orders. Validate instrument rules, price freshness, spread/liquidity, fees, slippage, margin/leverage, partial fills, rejects, timeouts and duplicate/unknown outcomes per venue.
7. **Cross-venue prices:** USDT targets USD parity but is not guaranteed exactly $1 everywhere. Common USDT quotation does not make prices/fills identical. Measure basis and execution drift; use explicit current conversion evidence for TMN or other quote assets.
8. **Release gates:** verify current-head PR #320 and exact-commit CI, then session isolation, freshness and execution safety. Keep live execution disabled until applicable gates pass.

## Acceptance sequence
- Confirm source contract and provider/venue/symbol/timeframe mapping.
- Validate timestamps, OHLC shape, closed-bar handling, gaps/staleness and reproducible source parity.
- Keep unknown sequence/volume semantics from blocking unrelated work; isolate dependent features.
- Review PR #320 with current commit evidence only.
- Prove session/connection isolation.
- Test execution adapters in read-only/test mode, including order/fill reconciliation and failure recovery.
- Maintain HOLD / NO_TRADE_ONLY until evidence proves the relevant safety gates.
