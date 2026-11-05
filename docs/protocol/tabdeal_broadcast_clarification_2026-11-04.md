# Tabdeal Broadcast sequence clarification — 2026-11-04

## Exact scope

- Venue/product: Tabdeal FAPI / Futures-Margin
- Endpoint: wss://api1.tabdeal.org/special_margin/broadcast/
- Subscription: raw-text BTC_USDT
- Message: trade envelope
- Field: trade.sequence
- Protocol version: unknown

## Exchange-response summary supplied by the project owner

The owner supplied a summary of an official written Tabdeal reply received on 2026-11-04:

1. trade.sequence is informational only. It is not globally, per-market, or per-connection unique.
2. It is not strictly consecutive, replayable, or a guaranteed gap detector.
3. Equal values are not automatically duplicate trades.
4. It is not an ordering guarantee or a deduplication key.
5. Depth sequence is independent and must not be compared with Broadcast trade.sequence.
6. Broadcast has no documented replay/gap recovery. Reconnect and resubscribe are required; approximate REST snapshot reconciliation is also required before dependent use.
7. Persist every full trade payload with market, local reception timestamp, and venue event timestamp.

## Evidence provenance limitation

The original response's sender/source metadata, exact full message, message/ticket identifier, and content hash are not available in this worktree. This file records an owner-supplied summary of an exchange response; it is not a pinned primary-protocol excerpt. Do not use it to claim a primary-source hash or promote registry capabilities to true. Keep the exact-scope registry conservative until the original evidence is attached and pinned.

## Collector policy

- Preserve the full raw payload as received, plus its exact-wire SHA-256.
- Persist market, venue event timestamp, local reception timestamp, connection epoch, and local receive ordinal.
- Preserve trade.sequence only as informational metadata; never use it for identity, ordering, deduplication, gap detection, or replay.
- Keep Depth sequence in a separate semantic scope.
- Mark every record decision_grade=false.
- Reconnect/resubscribe does not recover missed events. The required approximate REST snapshot reconciliation is not implemented in this collector.
- The collector remains disabled by default and is not connected to the live market-analysis or execution path.

Gate.io Public Spot BTC_USDT remains the sole authoritative live market-data source for candles, charts, and indicators. Execution is separate and is not authorized by this collector.