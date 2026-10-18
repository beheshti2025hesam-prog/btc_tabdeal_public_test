# Cross-venue sequence semantics research note

- Research date: 2026-10-15
- Status: research-only; no exchange contract is inferred from another venue
- Scope: HES Trade Agent, Tabdeal `special_margin/broadcast/`, `trade.sequence`
- Decision: keep ordering, continuity, and event-ID deduplication unauthorized for this Tabdeal field until Tabdeal-specific evidence proves the exact contract.

## Executive finding

The other-exchange evidence is useful for designing the adapter and recovery policy, but it cannot establish the meaning of Tabdeal's `trade.sequence`. The same short field names can represent distinct concepts even within one exchange. Treat the venue + product + endpoint + channel + message type + field path + protocol revision as the semantic scope.

## Saved exchange-support evidence

### Toobit

Saved support response for the project states that `v` is globally unique and increasing in the referenced Spot and USDT-margined markets, but is not necessarily contiguous for one trading pair; gaps can be natural. This is consistent with a global counter shared across symbols: a per-symbol observer may see gaps without missing a trade for that symbol.

A second saved Toobit response states that a reconnect only replays the most recent 60 trades, and that if more than 60 trades were missed there is no REST history/reconciliation path or documented method to prove complete alignment across the disconnect. Klines may help aggregate consistency checks but are not a substitute for complete individual trade history. Therefore a reconnect plus a plausible-looking ID sequence does not prove the trade stream is complete.

Official docs:
- Spot WebSocket trade stream: https://api-docs.toobit.com/api/spot-websocket-market-data
- USDT-M WebSocket trade stream: https://api-docs.toobit.com/api/usdt-m-websocket-market-data

The public Toobit docs describe trade-stream `v` as a globally incremented, unique transaction ID and show an example spanning different symbols. The same docs reuse `v` for depth/diff-depth version data and explicitly say those depth version values are not guaranteed unique. This is direct evidence that a field name alone does not define semantics; the channel and payload contract matter.

### Wallex

Saved project context says Wallex support explained that updates do not occur when no trade is executed. No exact Wallex support wording is preserved for identifier uniqueness, monotonicity, contiguity, reconnect recovery, or completeness. Do not upgrade this limited statement into a sequence guarantee.

Operational implication: event-driven silence can be normal during inactivity. It cannot be treated as a missing-message gap without an independent heartbeat, documented counter, or other explicit feed contract.

## Official cross-venue examples

- **Bybit public trades** documents both `i` (Trade ID) and `seq` (cross sequence). It also states that one message may contain up to 1024 trades and multiple messages may share the same `seq`. Thus `seq` is not a safe per-trade uniqueness key. Source: https://bybit-exchange.github.io/docs/v5/websocket/public/trade
- **Coinbase Exchange** trade-match messages carry `trade_id` separately from `sequence`; the matches channel warns messages can be dropped and recommends the heartbeat channel plus REST to recover missed trades. This is a documented recovery contract, not a rule transferable to Tabdeal. Source: https://docs.cdp.coinbase.com/exchange/websocket-feed/channels
- **Binance Spot** trade streams expose trade IDs, while order-book continuity uses the distinct `U`/`u` update range and snapshot `lastUpdateId`; a range gap requires resynchronization. Source: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

## Tabdeal evidence boundary

Official Tabdeal documentation describes `wss://api1.tabdeal.org/special_margin/broadcast/`, text subscription by market symbol, and `{"trade": {...}}` messages for new trades. It does not define `trade.sequence` as a unique trade ID, a per-symbol counter, a global counter, an ordered message sequence, or a contiguous gap-detection counter. A separate aggregate-depth REST example has a `sequence` field, but that is a different endpoint and payload and does not define the broadcast trade field.

Official source: https://docs.tabdeal.org/ (sections “وب‌سوکت اهرم حرفه ای” and “اردربوک تجمیع‌شده (Agg Depth)”).

## Adapter and safety consequences

1. Keep Tabdeal `trade.sequence` classified as unknown/opaque.
2. Do not sort trades, deduplicate events, flag conflicts, or infer gaps from that field.
3. Suppress exact replays only when a SHA-256 digest is computed at the raw transport payload boundary and the payload bytes match.
4. Build OHLC candles only when order is independently established. If equal timestamps with differing prices leave open/close order ambiguous, fail closed rather than tie-break by the opaque field.
5. Do not claim reconnect completeness unless a Tabdeal-specific replay/history contract and its boundary conditions are verified.
6. Any later capability authorization must be tied to exact immutable evidence: venue, product, endpoint, channel, message type, field path, protocol version, scope, source revision/hash, and independently trusted signer/key pin.

## What would change the decision

Acceptable evidence would be a Tabdeal-specific official schema or support response explicitly defining this exact field and scope, backed by representative raw message fixtures. For gap detection/recovery, it must also define counter scope, ordering/contiguity, reset/reconnect behavior, and a supported replay or reconciliation procedure. Sample numeric values alone are insufficient.

## Current decision

**HOLD / NO TRADE.** This note supports conservative implementation; it does not authorize live collection, registry promotion, merge, deployment, or trading.
