# Exchange Sequence Semantics — HES Research Digest

**Source artifact:** `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md`  
**Research version:** 1.0-draft  
**Retrieval date in source:** 2026-10-10  
**Scope:** Crypto Spot and derivatives WebSocket market data; Tabdeal Futures/Margin is the immediate case.  
**Classification:** Research digest, not a substitute for the complete source report or primary exchange documentation.

## Executive rule

A field named `sequence`, `seq`, `id`, `tradeId`, `u` or `updateId` has no generic meaning. Its semantics belong to the exact venue, product, endpoint, channel, message type, field path and protocol version. A numeric value alone does not prove uniqueness, ordering, contiguity, gap detection, replay behavior or comparability across reconnects.

## Key venue findings in the source report

- **Tabdeal Spot depth:** the reviewed sample contains event/time/symbol/bid/ask fields but no documented sequence/update range. No book-gap detection is supported by the reviewed contract.
- **Tabdeal FAPI/Margin depth:** the reviewed depth message has no documented sequence or update-range field. Reset/replay semantics are not documented.
- **Tabdeal aggregate-depth REST:** an example contains `sequence`, but uniqueness, ordering, continuity and relation to WebSocket messages are not documented.
- **Tabdeal FAPI/Margin broadcast trades:** the public page documents a `{"trade": {...}}` envelope but does not define the inner trade fields or `trade.sequence`. The field must remain opaque metadata. The project-owner-recorded official reply (2026-11-04) says not to assume uniqueness, ordering, consecutiveness, replay, gap detection or deduplication; depth sequence is separate and REST reconciliation is approximate.
- **Binance Spot depth:** the documented `U`/`u` update range and REST `lastUpdateId` synchronization procedure support channel-specific book continuity and gap recovery. Trade IDs are a different contract.
- **Binance COIN-M Futures:** `U`, `u`, `pu` depth linkage and `a`, `f`, `l` aggregate-trade identifiers have distinct meanings.
- **OKX:** `seqId`/`prevSeqId` are documented for specific book channels; maintenance resets and same-value keepalives are documented counterexamples to universal strictly-increasing logic.
- **Bybit:** `u` and `seq` have channel-specific semantics; repeated snapshots and multiple trades sharing a sequence value are documented.
- **Coinbase and Kraken:** each has its own feed/channel-specific sequencing, snapshot or checksum contract. These guarantees must not be generalized to other venues.

## Registry requirements

The registry key is the full tuple:

`(venue, product, endpoint, channel, message_type, field_path, protocol_version)`

Each positive capability requires a primary source URL, retrieval metadata, evidence excerpt and pinned content hash where tooling permits. `unknown` is a first-class state and is not the same as `false`. A field may have multiple records when its meaning changes by product or channel. Protocol drift must fail closed when a required field disappears, changes wire type, nesting or documented scope.

## Normalized event and capability model

Preserve raw payload evidence and keep identity, ordering and book-update capabilities separate. The source report proposes normalized fields for venue/product/endpoint/channel/symbol, connection/session IDs, message type, receive time, venue timestamp, optional identity, optional ordering evidence, optional book-update evidence, raw-payload hash and registry revision.

Adapters declare only evidenced capabilities, such as exact-replay deduplication, documented event-ID deduplication, within-scope ordering, within-scope contiguity, book-range gap detection, previous/current linkage, checksum validation and snapshot reset. The generic layer must never infer a capability from a field name.

For Tabdeal FAPI/Margin broadcast, the conservative profile is: `trade.sequence` remains unknown/opaque; event-ID deduplication, ordering, contiguity and book-gap detection are disabled unless a newer documented contract proves them. Exact raw-payload replay may be handled separately if the adapter explicitly supports it.

## Decision and recovery rules

- Exact raw-payload replay may be ignored idempotently where the message contract permits; record a replay metric.
- A repeated value with a different payload is a conflict only when that field is proven to be an identity key in the relevant scope.
- A numeric gap is actionable only for a registered contiguous range/link field.
- On reconnect, create a new connection/session epoch, resubscribe and obtain a fresh snapshot when required. Do not compare identifiers across sessions unless the registry explicitly permits it.
- Stale data, heartbeat timeout, missing required fields, unknown schemas, clock anomalies, invalid checkpoints, checksum mismatches and protocol drift block dependent processing.
- A stateful book must be re-synchronized before dependent strategies resume. The affected path remains `NO_TRADE_ONLY` while evidence is invalid or incomplete.

## Required test vectors

The source report defines deterministic cases for opaque repeated values, exact replay, conflicting documented identities, missing fields, Binance Spot range application and gaps, OKX keepalive and maintenance reset, Bybit repeated snapshots and trade batches, Kraken checksum mismatch, JSON boolean/integer pitfalls, timestamp units, reconnect epochs, snapshot resets and corrupt checkpoints.

Property-based invariants include: unknown/non-contiguous fields must never infer loss from arithmetic; scope changes must prevent cross-scope comparison; exact replay must be idempotent only where supported; book ranges must follow the documented relation; timestamp normalization must not create ordering capability; and schema drift must be surfaced.

## Maintenance

Treat protocol semantics as versioned evidence, not permanent prose. Re-check official documentation and changelogs on a schedule, record retrieval date and content hash, compare schema fingerprints, run replay fixtures and publish a changelog. Freeze an affected adapter revision when its documented contract drifts.

## Limitations

This digest summarizes the supplied research artifact. It does not independently re-verify every cited exchange page on 2026-11-19 and does not itself authorize any live adapter, book-state mutation, order or production release. Always consult the exact current primary contract before enabling a capability.
