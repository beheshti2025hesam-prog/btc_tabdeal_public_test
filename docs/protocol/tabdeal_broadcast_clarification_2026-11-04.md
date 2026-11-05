# Tabdeal Broadcast sequence clarification — 2026-11-04

## Exact scope

- Venue/product: Tabdeal FAPI / Futures-Margin
- Endpoint: wss://api1.tabdeal.org/special_margin/broadcast/
- Subscription: raw-text BTC_USDT
- Message: trade envelope
- Field: trade.sequence
- Protocol version: unknown

## Verbatim exchange reply body — pinned 2026-11-05

The project owner supplied the full Persian response body and attributed it to Tabdeal official written reply received on 2026-11-04. The exact body is preserved at:

- docs/protocol/evidence/tabdeal_broadcast_reply_2026-11-04.fa.txt
- SHA-256 (UTF-8 bytes including final LF): bd83b1b70b1518937d805733d92e570c98311ea5dd8bc7c3d9f8dc6d0c3a53cd
- Metadata: docs/protocol/evidence/tabdeal_broadcast_reply_2026-11-04.metadata.json

The response explicitly says trade.sequence is informational metadata only; it is not a documented globally/per-market/per-connection unique trade ID, strict ordering/consecutiveness guarantee, replay cursor, gap detector, or safe deduplication key. Equal values must not cause automatic duplicate removal; a numeric jump must not automatically be interpreted as a lost trade; each received trade is an independent event. Depth sequence is separate. Broadcast replay/gap recovery is undocumented; reconnect/resubscribe plus approximate REST snapshot reconciliation is the advised procedure, not guaranteed lossless recovery. Every trade payload, market, reception timestamp and event timestamp should be persisted.

### Provenance boundary

This is the verbatim response body supplied by the project owner and attributed to an official Tabdeal reply. The original sender headers, email/ticket identifier and transport metadata were not included. The body hash is pinned; source-header provenance is not. Do not invent missing sender or ticket metadata. The exact-scope registry therefore retains conservative unknown capability values: absence of documented guarantees is not proof that a capability is technically impossible.

## Collector policy

- Preserve the full raw payload as received, plus its exact-wire SHA-256.
- Persist market, venue event timestamp, local reception timestamp, connection epoch, and local receive ordinal.
- Preserve trade.sequence only as informational metadata; never use it for identity, ordering, deduplication, gap detection, or replay.
- Keep Depth sequence in a separate semantic scope.
- Mark every record decision_grade=false.
- Reconnect/resubscribe does not recover missed events. The required approximate REST snapshot reconciliation is not implemented in this collector.
- The collector remains disabled by default and is not connected to the live market-analysis or execution path.

Gate.io Public Spot BTC_USDT remains the sole authoritative live market-data source for candles, charts, and indicators. Execution is separate and is not authorized by this collector.
