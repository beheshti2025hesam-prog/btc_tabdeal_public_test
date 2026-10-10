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


## Integration with the existing evidence boundary (Issue #70)

This contract must feed the existing `CanonicalTrade`, `DataQualityReport`, and `EvidenceSnapshot`/`EvidenceRegistry` path. It does not introduce a second evidence registry or replace Raw Data as the source of truth.

### Identity and provenance mapping

| Concept | Canonical meaning | Constraint |
|---|---|---|
| `receipt_id` | HES-local durable identity for one accepted inbound receipt record | Unique within a documented durable namespace; never presented as an exchange ID |
| Native `event_id` / `sequence` | Source-provided identifiers copied without reinterpretation | Preserve type and original representation; semantics are contract-versioned and may remain UNKNOWN |
| `ingested_at` / receive time | UTC time HES recorded receipt | Distinct from source event time; retain precision and clock-health metadata |
| Raw evidence reference + SHA-256 | Immutable original message/file bytes or an explicitly versioned privacy-safe representation | Hash exact stored bytes; never hash a silently normalized or rewritten substitute |
| `collector_run_id` / connection epoch | Collection attempt and connection lifetime provenance | If unavailable, encode null plus a reason; never fabricate an ID |
| Dataset manifest hash | Fingerprint of the exact raw inputs selected for one evaluation | Bind relative path, byte length, SHA-256 and evidence role; deterministic UTF-8 canonical serialization, stable key ordering, and lexicographically sorted normalized relative paths |
| Canonical dataset hash | Fingerprint of the derived canonical records actually evaluated | Separate from raw-manifest hash; record canonicalization/schema version and deterministic record ordering |
| `DataQualityReport` hash | Exact quality report used by the evaluation | Hash its canonical serialized representation and bind it to the raw-manifest hash and report/schema version |
| `EvidenceSnapshot` | Existing evidence record for a specific evaluation | Bind dataset-manifest hash, canonical-dataset hash when available, evaluation window, run IDs, source bounds, quality-report hash, code commit and classification |

Hashing rules: SHA-256 is applied to exact raw bytes for raw artifacts. Structured manifests/reports use a named, versioned canonical serialization before hashing; the serialization version is itself recorded. File paths are relative to a declared evidence root and may not escape it. The manifest records missing/unreadable inputs as explicit errors rather than silently omitting them. No filesystem enumeration order, locale, wall-clock value, or unstable map iteration may affect the hash.

### Evaluation boundary and classification

- Define evaluation windows as UTC half-open intervals `[start, end)`; record both endpoints and the timezone/precision contract. If a legacy evaluator cannot provide a window, mark it UNKNOWN instead of inferring one.
- Keep three layers distinct: immutable raw receipts/files; canonical normalized records; and any deduplicated/filtered evaluation view. Every transformation must name its version and produce a manifest/hash linking its inputs to outputs. Deduplication must not delete or rewrite raw evidence.
- Bind `DataQualityReport` to the exact raw manifest, canonicalization version and evaluation window it assessed. A report from another dataset/window is not interchangeable.
- Use explicit evidence classifications such as `OBSERVED_ANOMALY`, `SUSPECTED_COVERAGE_LOSS`, `CONFIRMED_INTEGRITY_FAILURE`, and `UNRESOLVED`. A sequence discontinuity alone remains an observed anomaly unless a reviewed, source-specific contract establishes that the feed guarantees the relevant continuity.
- A trusted evaluation snapshot must fail closed if required hashes, source/run provenance, code commit, evaluation window, or report linkage are absent or inconsistent. Optional fields may be null only with an explicit reason and must not satisfy a safety-critical gate.
- Regression tests must prove detection of byte tampering, manifest/path changes, stale code commits, dataset/window/symbol/venue mismatch, quality-report mismatch, missing run IDs, nondeterministic ordering, and anomaly-versus-confirmed-loss misclassification. Tests use synthetic fixtures and never rewrite production evidence.

## Normative local receipt-journal requirements (design gate)

The following requirements are normative for any future durable receipt-journal implementation. They define acceptance criteria, not permission to deploy or to collect live data.

### Identity unit and namespace
- A `receipt_id` identifies exactly one **accepted receipt record** in HES, not a transport frame by implication and not an exchange event ID. The adapter must explicitly state whether one inbound frame can decode to zero, one, or multiple events.
- If one frame yields multiple events, preserve a stable frame-level evidence reference and assign a distinct receipt ID to each accepted event record; record the relationship without claiming the events were separately transmitted.
- The durable namespace must include a journal/schema identity and must survive process restarts. IDs must be strictly non-reused within that namespace. An in-memory counter or receive ordinal alone is not durable identity.
- Allocation order is local acceptance order only. It must never be represented as upstream ordering or completeness evidence.

### Append and commit protocol
- A receipt is **accepted/issued** only after the complete record and its integrity metadata have crossed the storage backend's documented durability boundary. The implementation must document the actual primitive and its guarantees; a successful language-level write call alone is not proof of durable commit.
- Serialize writers. A second writer must fail closed before appending; it must not race to allocate IDs or append to the same journal.
- After restart, recover the next ID only by validating the durable journal and its namespace/schema metadata. Never silently truncate, rewrite, or repair a partial/corrupt tail.
- On partial write, flush/fsync failure, disk-full, lock ambiguity, or corrupted tail, stop accepting receipts and report a persistent degraded/integrity-failure state. Preserve the bytes available for forensic recovery.
- If a write's commit outcome is ambiguous, reconcile the intended record against the validated durable journal before retrying. Do not blindly allocate a new ID; if exact reconciliation is impossible, fail closed and require explicit recovery.
- An existing receipt ID associated with different content is a hard integrity conflict. Identical retry content may be treated as an idempotent retry only after checking the durable journal; it must not create a second logical receipt silently.

### Time and evidence representation
- Store UTC wall-clock receive time separately from a monotonic elapsed-time measurement and identify the clock/boot epoch needed to interpret the monotonic value. Monotonic values are for elapsed-time diagnostics, not cross-boot timestamps.
- Wall-clock rollback, large skew, missing monotonic continuity, or unknown clock health must never make old data appear fresh or prove continuity. Mark freshness/continuity as unknown or degraded.
- State the evidence representation for each privacy mode. If only a decoded or sanitized representation is retained, version its canonical encoding and hash exactly those stored bytes; explicitly do **not** label that digest as a hash of the original transport frame.
- When the received message is text re-encoded as UTF-8, name that representation precisely. It is not a wire-byte hash unless the transport layer actually exposes and preserves the original wire bytes.

### Required synthetic fault-injection tests
Before any implementation is considered reviewable, tests using temporary synthetic files only must cover:
1. Failure at partial write, flush/fsync, and commit boundaries; no success/receipt issuance on uncommitted data.
2. Restart recovery from a valid journal and from a partial or corrupt tail; no silent repair and no ID reuse.
3. Ambiguous-commit retry, exact duplicate retry, and same-ID/different-content conflict.
4. Monotonic ID allocation across restart and journal/schema namespace mismatch.
5. Concurrent writer/lock contention; only one writer may append.
6. Wall-clock rollback/skew and monotonic clock/boot-epoch discontinuity.
7. Disk exhaustion and persistence errors; accepting stops immediately and health stays degraded.
8. Multi-event frame identity relationships, if the adapter can decode multiple events from one frame.
9. Privacy-mode representation/hash correctness, including a test proving that a sanitized-message hash is not described as an original-frame hash.
10. Append-only guarantees: prior committed records remain byte-identical after every injected failure.

These tests validate HES's local persistence behavior only. They do not establish Tabdeal Futures `trade.sequence` semantics, upstream delivery completeness, or authorization to start the 48-hour observation.
 
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
