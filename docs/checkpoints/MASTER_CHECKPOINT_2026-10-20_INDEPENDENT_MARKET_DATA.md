# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-20  
**Decision:** Exchange-independent market intelligence + strategy/risk brain + venue-specific execution  
**Runtime state:** HOLD / NO_TRADE_ONLY

## Durable principles
- Memory = project map/continuity; GitHub = technical truth; Chat = conversation log; Master checkpoint = restart point.
- No invented facts, endpoints, guarantees, test results, approvals or success claims.
- Do not make routine progress depend on exchange-support emails or replies.
- Prioritize TradingView or a comparable documented global chart/data source; feed validated market data and approved news/context into the strategy/risk brain.
- Send approved trade proposals through modular venue-specific private API adapters; actual order state/fills remain venue truth.
- USDT targets USD parity but is not guaranteed exactly $1 everywhere. USDT quote denomination does not equal identical prices or fills across venues.

## Target architecture
1. **Intelligence layer:** documented candles/prices and approved news/context with provider, instrument, timeframe, timestamps and quality metadata.
2. **Strategy/risk layer:** compute direction, proposed entry, stop-loss, take-profit, size and limits.
3. **Execution layer:** venue-specific private APIs; validate live executable price, instrument rules, spread/liquidity, fees, slippage, margin/leverage and reconcile acknowledgements/orders/fills.

## Dependency decisions
- Ordinary candle-first analysis does not require undocumented sequence semantics.
- Unexplained volume does not block the core candle pipeline; preserve raw volume and gate volume-sensitive features.
- Sequence/order-book handling is a narrow adapter-specific requirement only for features that truly need it.
- Support outreach is optional and only justified for essential safety-critical capabilities that cannot be proven otherwise.
- A global signal does not guarantee execution at another venue; check basis, freshness, latency, spread and slippage.

## Roadmap
1. TradingView or comparable chart/data-source integration.
2. Prove candle mapping, time alignment, finality, freshness, gap handling and source/chart parity.
3. Route validated data plus selected news/context into strategy/risk.
4. Verify modular private-API adapters and order/fill reconciliation.
5. Review PR #320 against current-head code and CI; do not reuse old-head evidence.
6. Prove session isolation and execution safety.
7. Keep live execution disabled until acceptance gates are proven.

## Evidence and open items
- This checkpoint records an architecture decision; it does not certify all components as implemented.
- PR #320 remains Draft/unmerged per the latest fetched PR record. Its description reports 27/27 Actions success for commit `bbf61f55926e5af0f4cf1d07894bbdb40ff5234c`; the latest PR head returned by GitHub during this checkpoint is `3db53e56f476863a60c2df16e272c961dd2e50b3`. Those are different commits, so the older CI report must not be represented as current-head CI.
- Prior live evidence described 80/80 overlapping closed 1m bars matching trade-derived OHLC and a persistent 2x Wallex UDF-volume factor; the volume cause remains unknown. This is not a blocker for the candle-first core, but it blocks relying on that volume for volume-sensitive features.
- Production WebSocket reconnect/session isolation remains unverified; a deterministic harness is not proof of production collector isolation.
- No live trading, deployment, credential changes or collector activation is authorized by this checkpoint.

## Next action
Continue from the current PR head: inspect exact commit/CI, finish PR #320 review, and close only evidenced gaps. Do not restart support-email follow-ups or reopen sequence/volume as global blockers.
