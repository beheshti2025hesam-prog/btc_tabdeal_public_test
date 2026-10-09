# Provider-Neutral Market-Data Contract v1 — Design Proposal

**Status:** design only; not implementation or permission to run a collector.  
**Date:** 2026-10-10  
**Safety boundary:** Tabdeal Futures `trade.sequence` semantics remain unverified. Its reviewed evidence pin stays unset, the observation gate stays closed, and the 48-hour observation remains NOT STARTED.

## Invariants
- No trading execution, order endpoints, strategy/threshold tuning, risk-gate changes, or production/VPS changes under this proposal.
- Preserve source evidence append-only and hash-verifiable; never silently repair, reorder, or delete events.
- A contract applies only to its exact provider, venue, product, channel/endpoint, symbol, and schema version. Similar field names do not imply equivalent semantics.
- Same-venue completeness and cross-venue corroboration are separate claims. Another venue must never fill or certify missing Tabdeal Futures events.
- Unknown schema/mapping, stale data, source conflict, or unproven gap means explicit uncertainty; decisions requiring that data fail closed to `NO_TRADE`, execution disabled.
- Prefer public/free access. Any future paid source remains an optional adapter, not a core dependency.

## Adapter boundary
An adapter only connects to one documented feed, validates its native schema, preserves provenance, emits normalized events and health states, and exposes documented recovery capabilities. It does not calculate signals or decide whether to trade.

Proposed logical operations:
- `describe_contract()`: provider/product/channel identity, schema version, identifier and timestamp semantics, recovery capabilities, limits, and known unknowns.
- `connect()`: read-only connection.
- `decode(message, received_at_utc)`: validate and normalize without inventing missing values.
- `recover(cursor, interval)`: use only documented recovery semantics; otherwise return `RECOVERY_UNSUPPORTED`.
- `health()`: connection epoch, freshness, event/receive progress, gap/conflict state, and recovery status.
- `close()`: orderly shutdown; no hidden autostart.

## Event envelope
Each event should include:
- `schema_version`, `provider_id`, `venue_id`, `product_type`, `market_id`, native symbol, mapping version;
- event type, native event ID and native sequence as opaque optional values;
- UTC event time and receive time, with source semantics and precision documented;
- connection epoch and local receive ordinal (audit ordering only; not proof of upstream order);
- immutable evidence reference and SHA-256, or a documented privacy-safe evidence representation;
- source health, coverage, decode status, reconciliation reference, and the original native fields needed for audit.

Native IDs/sequences must not be assumed unique, dense, monotonic, or replayable unless the exact source contract proves it. Do not use floating-point rounding as event identity. Do not substitute receive time for missing event time.

## Local receipt identity, idempotency and gap observability

HES should assign each successfully accepted inbound message/event a locally generated, unique, durable `receipt_id`. This identifies HES's receipt record only; it is not a substitute for, or a claim about, the exchange's native trade ID or sequence.

- Define the receipt-ID uniqueness scope and persistence model explicitly. IDs must not be reused after process restart; an in-memory counter alone is insufficient for durable identity. Concurrency and single-writer behavior must be specified and tested.
- Preserve the native event ID/sequence as opaque source fields, along with provider/venue/product/symbol, schema version, UTC source event time, UTC receive time, connection epoch, source provenance, and immutable evidence/hash reference.
- Keep deduplication separate from receipt numbering. Deduplicate only where documented native identity semantics or a validated idempotency key justify it. Equal timestamps/prices/quantities alone do not prove two messages are the same trade. Conflicting records must remain auditable rather than being silently discarded.
- Track duplicate deliveries, out-of-order arrivals, source-sequence anomalies, suspected/confirmed gaps, reconnects, stale feeds, and unresolved conflicts as distinct outcomes. A local receipt counter must not be used as a proxy for source sequence continuity.
- **Critical limitation:** consecutive local receipt IDs prove only that HES numbered the records it received. They cannot prove that the upstream venue emitted every event or detect a message lost before HES received it. Upstream completeness requires a separately verified source contract and/or documented same-venue reconciliation.
- On identity ambiguity, persistence failure, suspected gaps, unknown sequence semantics, or unresolved conflict, preserve evidence and expose an explicit degraded/blocked health state. Fail closed for dependent decisions (`NO_TRADE` where applicable); execution remains disabled until the relevant gate passes.

## Source-contract registry
For every provider/product/channel, record:
1. Official documentation URL and retrieval date/hash.
2. Product scope, symbol mapping, native identifier and sequence semantics (scope, density, reset/reconnect behavior).
3. Event/publication timestamp meaning, timezone and precision.
4. REST history depth, cursor boundaries, pagination and replay limitations.
5. WebSocket subscription, heartbeat, connection lifetime, reconnect/resubscribe and replay guarantees.
6. Public/auth requirements, endpoint-specific limits, regional/VPS reachability test date, known gaps and explicit non-guarantees.
7. Reviewer and immutable evidence reference for claims that unlock a safety-critical gate.

Undocumented properties stay UNKNOWN. Spot documentation cannot prove Futures semantics, and one endpoint cannot prove a different feed's contract.

## Health and reconciliation
Use explicit states: `HEALTHY`, `STALE`, `DISCONNECTED`, `RECONNECTING`, `GAP_SUSPECTED`, `GAP_CONFIRMED`, `CONFLICT`, `SCHEMA_UNKNOWN`, `DECODE_FAILED`, `RECOVERY_UNSUPPORTED`, and `CROSS_VENUE_DIVERGENCE`.

- Do not infer a confirmed gap from a numerical sequence gap unless the exact feed's documented contract supports that inference.
- Do not infer health merely because messages arrive.
- Same-venue recovery requires proven identity and documented equivalence of product, event scope, IDs, timestamps and coverage. Otherwise treat the source as corroboration only.
- Preserve duplicates and conflicting records; record reconciliation outcomes before any downstream decision.
- Recovery reports must state covered/uncovered intervals, cursor bounds, duplicates, unresolved gaps and evidence hashes.
- Cross-venue comparisons require explicit product/symbol mapping. Never match trades by timestamp/price/size alone, silently fill venue-specific gaps, or claim venue-specific order-book/liquidity completeness from another venue.

## Deterministic acceptance tests (synthetic fixtures; no network by default)
1. Schema changes, missing fields, and unknown versions fail explicitly.
2. Identical duplicate IDs are classified; conflicting payloads under one ID preserve both evidence references and raise conflict.
3. Repeated, sparse, decreasing, reset, per-symbol or connection-scoped sequences remain uninterpreted unless the fixture's reviewed contract defines them.
4. Equal timestamps, out-of-order arrival, clock skew and timestamp precision loss remain distinguishable.
5. Pagination inclusive/exclusive boundaries, overlaps, empty pages, repeated boundary events and pagination stalls are deterministic.
6. Reconnect creates a new connection epoch; unsupported replay leaves an explicit unresolved interval.
7. Freshness tests cover stale feeds, heartbeat-only progress and frozen event timestamps.
8. Cross-source tests cover product/symbol mismatch, Spot-vs-Futures mismatch, timestamp mismatch, divergence and source outage.
9. Any unresolved safety-critical state prevents a trusted snapshot and keeps `NO_TRADE`; no test enables execution.
10. Append-only persistence, hashes, crash boundaries, malformed records and concurrent-writer attempts are tested without touching production evidence.
11. Rate-limit backoff and regional failures are simulated; any later live canary is opt-in, bounded, read-only and timestamped.

## Rollout gates
1. Review and freeze this contract.
2. Complete provider-specific official-source records, retaining explicit unknowns.
3. Implement pure normalization tests and deterministic health/reconciliation tests.
4. Submit a small opt-in read-only adapter PR for independent review; no production autostart.
5. Only after review, run a bounded isolated canary with explicit rate limits and abort conditions.
6. Production observation remains prohibited until Tabdeal sequence semantics, single-writer safety, evidence integrity and operational readiness gates independently pass.

## Current provider disposition
- **Tabdeal Futures broadcast:** blocked for completeness-sensitive observation pending authoritative semantics for the exact feed.
- **Binance Spot:** first candidate for a separate market-context adapter; not a replacement for Tabdeal Futures.
- **Coinbase:** secondary candidate; channel-specific replay/reconnect and limits need further review.
- **Kraken Spot:** secondary candidate; timestamp pagination boundaries and operational reachability need validation.

This proposal approves no provider, changes no current gate, and makes no claim of VPS reachability.
