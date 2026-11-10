# HES Trade Agent — Project DNA

## Team and operating model
The project team consists of exactly two collaborators in its operating plan:
- **Project owner:** sets priorities and makes project decisions.
- **AI engineering partner (ChatGPT):** advances technical analysis, planning, implementation, code review, test design, and evidence checks.
Do not plan routine execution around an assumed third team member. Prefer autonomous progress with minimal owner intervention.

## Core architecture — exchange-independent market intelligence
HES is designed as three decoupled layers:

1. **Market-data/intelligence inputs:** trusted, documented market-data and chart sources for candles/prices, plus approved news/context. TradingView or a comparable global charting/data source is a high-priority roadmap integration. Always record provider, venue/instrument, timeframe, timestamp and limitations; do not call a provider universally authoritative for every instrument without evidence.
2. **Strategy/risk brain:** validate and normalize inputs, evaluate context and strategy, then calculate proposed direction, entry, stop-loss, take-profit, sizing and risk limits. Ordinary candle-based analysis must not depend on undocumented exchange sequence fields or unexplained volume semantics.
3. **Venue-specific execution adapters:** private APIs handle order submission, order status, fills and other explicitly authorized account operations. Each adapter validates instrument mapping, precision/minimums, supported order types/position mode, current executable price, spread/liquidity, fees, slippage, funding and margin/leverage rules where applicable. Actual venue order state and fills—not the global chart—are the execution truth.

A global market-data source does not mean every venue has identical prices or fills. Preserve venue-specific mappings and measure basis/spread, staleness, latency and execution drift.

## Non-blocking exchange support and undocumented semantics
- Do **not** make routine project progress depend on emailing exchange support or waiting for replies. Support correspondence is optional evidence, not a workstream or prerequisite by itself.
- Do not repeatedly chase unanswered questions when the feature can be built from documented capabilities or safely excluded.
- An unanswered question remains **unknown**; continue the exchange-independent core and other adapters.
- Sequence-like fields are not generically required for ordinary candle construction, chart display or candle-based strategy analysis. Never infer uniqueness, ordering, contiguity, gap detection or cross-session comparability from a field name.
- An unexplained volume discrepancy does not block the core candle pipeline when a trusted candle source provides candle values. Preserve source volume as reported, mark semantics unknown and disable volume-dependent features until meaning/units are established.
- Sequence/order-book semantics remain adapter-specific only for features that truly need a stateful order book. Unknown semantics should disable the affected feature/path, not stall unrelated work.
- Seek exchange clarification only when a specific safety-critical capability is necessary and cannot be established from public contract plus reproducible evidence. Never invent API endpoints, semantics or guarantees.

## USDT and cross-venue pricing
USDT aims to track USD; it is not guaranteed to equal exactly USD 1 at every venue and moment. A common USDT quote does not make BTC/USDT prices, liquidity, spreads, fees or fills identical across exchanges. Local supply/demand, latency, funding and execution conditions still matter. For non-USD quote assets such as TMN, require an explicit conversion model and current FX evidence.

## Roadmap priorities
1. Integrate TradingView or a comparable documented chart/market-data source.
2. Validate canonical candle mapping, timestamps, closed-bar finality, freshness, gaps and source-to-chart parity.
3. Route validated candles plus approved news/context into the strategy/risk engine.
4. Keep ordinary candle construction independent of undocumented sequence fields and unexplained volume; gate only features that need those semantics.
5. Verify modular private-API execution adapters for selected domestic and international venues, including order/fill reconciliation.
6. Review PR #320 against this architecture using current-head evidence and CI for the exact commit; never reuse old-head test claims.
7. Verify session isolation and execution safety before enabling any live path.
8. Maintain HOLD / NO_TRADE_ONLY until applicable acceptance gates are proven.

## Review, security and evidence policy
- ChatGPT must not represent its review as independent third-party human review.
- CI/tests prove only the exact commit and scope actually run.
- Tie claims to verifiable commit IDs and source evidence; distinguish completed, proposed and unverified work.
- Do not claim tests ran if unavailable. Never fabricate approvals or imply unavailable people will act.
- No release gate passes on confidence, a green badge or a hash alone; stated security properties must be demonstrated.
- Documentation/tests do not authorize live collection, account access, VPS changes or trading.
- Keep credentials least-privilege and out of logs/repository files. Before live execution require risk limits, idempotent order handling, fill/order reconciliation, stale-data protection, kill switch and tested failure recovery.

## Communication
Report briefly and plainly: what changed, exact evidence, remaining uncertainty and next action. Never claim a GitHub change succeeded before its result is confirmed.


## Delivery deadline — 2026-11-19
The HES Trade Agent application delivery target is **19 November 2026 (28 Aban 1405)**. Delivery planning is a standing project constraint. Milestones: **22 Oct** verify the actual authorized frontend entry point; **26 Oct** deliver the first usable read-only chart slice; **16 Nov** release candidate; **19 Nov** delivery. These are targets, not claims that implementation is already complete. If no existing frontend can be verified, record the smallest explicit architecture decision needed; do not invent a frontend path or silently start a parallel app. Routine exchange-support emails, undocumented sequence semantics, and unresolved volume semantics must not distract from this critical path.
