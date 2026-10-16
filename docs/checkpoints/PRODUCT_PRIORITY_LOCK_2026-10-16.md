# HES Trade Agent — Priority Lock (2026-10-16)

## User-approved product priority — binding for future work
**Primary path:** Use official exchange/broker market data that powers its own chart/candlesticks, prioritizing OHLCV (Open, High, Low, Close, Volume) and timestamps for market analysis and signal development. First inspect the existing code and official API/SDK/documentation, then validate received candles against the same instrument and timeframe shown by the platform.

**Explicit de-prioritization:** `trade.sequence` is NOT the main project priority. The user is tired of spending approximately a month on this unresolved topic. Do not let it dominate planning, progress reports, or block unrelated work on candle ingestion and strategy development.

**Sequence's limited role:** Keep `trade.sequence` as a secondary integrity/security check only where evidence shows it is necessary. Do not claim its meaning is established without an authoritative contract. Do not repeatedly re-investigate it absent a concrete dependency or new evidence.

## Required execution behavior
1. Inspect the repository's current OHLCV/candle acquisition paths first; reuse existing work and avoid duplicate tests.
2. Verify official endpoints/SDK paths and symbol/timeframe/timestamp/closed-candle semantics.
3. Build validation around candle completeness, duplicates, gaps, timezone alignment, and comparison against the exchange/broker chart.
4. Use validated candles for strategy and signal development.
5. Keep safety gates appropriate to the risk, but do not confuse unresolved `trade.sequence` semantics with the primary product goal.
6. Report progress in simple language; distinguish verified facts from estimates.
7. Do not activate live trading or promote to production until the relevant data, security, and risk gates are actually satisfied.

## Project memory rule
- Memory = project map.
- GitHub = technical source of truth.
- Chat = conversation log.
- This file is the authoritative priority reminder for future HES Trade Agent work.
