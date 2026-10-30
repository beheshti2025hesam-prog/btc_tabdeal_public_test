# Exchange Sequence Semantics Registry v1

## Purpose and boundary

This registry prevents a field named `sequence`, `seq`, `id`, `tradeId`, `u`, or `updateId` from acquiring meaning outside its exact venue contract. A record is keyed by venue, product, endpoint, channel/topic, message type, field path, and protocol version. Unknown semantics are a first-class state, not a false/true guess.

HES's current live chart, candle, and indicator path is Gate.io's persisted closed OHLCV feed. Candle open time is a bucket key, not an event sequence. The registry does not introduce a second candle source or require reconstructing candles from trades. Execution remains a separate exchange-adapter boundary.

## Registry statuses

- `UNKNOWN`: public evidence does not define the field's semantics. No sequence-derived ordering, gap detection, deduplication, or conflict rule is enabled.
- `SOURCE_REVIEWED_UNPINNED`: a primary source was reviewed, but its exact content hash is not pinned. Claims are informational only and cannot be resolved into runtime capabilities.
- `VERIFIED`: exact scope, primary-source content hash, independent review revision, and code-pinned registry hash are present. Only explicitly listed capabilities may be returned.
- `RETIRED`: protocol drift or a superseding revision invalidates the old record.

The runtime loader checks the registry's SHA-256 against the code-pinned digest. A `VERIFIED` record must also have a primary HTTPS source, source-content SHA-256, independent review revision, internally consistent claims, and an exact key match. The registry cannot promote a record by field name alone.

## Current audited matrix

The machine-readable records are in `forward/sequence_semantics_registry_v1.json`.

| Venue / product / channel | Field or key | Current disposition |
|---|---|---|
| Tabdeal Spot depth | no sequence field in reviewed sample | Unknown; timestamp is not a sequence |
| Tabdeal FAPI depth stream | no sequence/update range in reviewed sample | Unknown; no REST/WS linkage |
| Tabdeal FAPI aggregate-depth REST | `sequence` | Opaque; no scope, uniqueness, continuity, or WS linkage claim |
| Tabdeal FAPI broadcast trades | `trade.sequence` | Opaque; inner trade schema and reconnect/replay contract undocumented |
| Binance Spot raw trade / aggTrade | `t` / `a` | Trade identifiers; never promoted to book-gap sequence |
| Binance Spot diff depth | `U..u` | Documented book update range and REST snapshot bootstrap; source hash still must be pinned before runtime use |
| Binance USDⓈ-M diff depth | `U..u; pu` | Exact current source/schema pin required before enabling |
| OKX books | `prevSeqId -> seqId` | Linked per-instrument updates; equality keepalive and maintenance reset are distinct states |
| OKX public trades | `tradeId` | Trade identifier, not books sequence |
| Bybit orderbook | `u; seq` | Update ID plus cross-sequence; repeated snapshots and restart reset are channel-specific |
| Bybit public trades | `i; seq` | Trade ID and cross-sequence are separate; multiple messages can share `seq` |
| Coinbase Exchange feed | `sequence` | Per-product contiguous sequence for covered Exchange feed messages; not transferable to Advanced Trade |
| Coinbase Advanced Trade | channel-specific | Unknown unless the exact channel schema is pinned |
| Kraken Spot v2 book | CRC32 checksum | Checksum capability, not numeric sequence |
| Kraken Futures book | `seq` | Field exists; stronger uniqueness/contiguity/cross-session claims remain unverified |
| Gate.io Spot candles | candle open time `t` | Time-bucket key only; current HES market-data path uses closed OHLCV candles |

All source-reviewed records remain non-executable until their exact primary source snapshot is pinned and independently reviewed. The current Tabdeal broadcast record is deliberately `UNKNOWN`; the default runner therefore blocks before network or session creation.

## Runtime rules

- `SequenceIntegrityV2` accepts only a verified scalar `ORDERED_EVENT_SEQUENCE` contract. It rejects timestamps, opaque identifiers, book ranges, link sequences, and checksum contracts.
- A numeric jump is not a missing event unless the exact record grants both `contiguous` and `contiguous_gap_detection`.
- A repeated value is not a conflict unless `event_identity` is verified in the same scope.
- Exact raw-payload replay is a separate capability and requires the raw payload hash; normalized field equality is not a substitute for raw-byte identity.
- Scope includes the registry-declared venue/product/channel/symbol/session dimensions. A changed scope blocks comparison; reconnect starts a new epoch unless a record explicitly authorizes cross-session comparison.
- Boolean, float, numeric-string, missing, and negative values are not silently coerced into integer sequence IDs.
- Book range, linked-book, snapshot-reset, and checksum semantics require their own specialized validators. They must not be routed through the scalar sequence state machine.

## Adding or updating a venue

1. Capture the exact product, endpoint, channel/topic, message type, field path, wire type, and protocol version.
2. Read the official primary source for that exact channel. Do not transfer Spot semantics to Futures, Exchange to Advanced Trade, or trades to order-book channels.
3. Record source URL, retrieval time, exact excerpt, source-content SHA-256, and independent review revision.
4. Add deterministic fixtures for normal, duplicate, gap, backward/reset, reconnect, missing-field, type-drift, and cross-scope cases as applicable.
5. Keep the record `SOURCE_REVIEWED_UNPINNED` until source hash and review are complete. Only then can a code change pin the new registry SHA-256.
6. Implement the correct specialized adapter. Do not use `SequenceIntegrityV2` for book ranges, links, timestamps, or checksums.
7. Run exact-head unit, integration, static, and CI tests. A market-data adapter does not grant execution permission.
8. Keep execution OFF until a separate venue decision, authenticated lifecycle/reconciliation proof, instrument filters, idempotency, paper soak, and owner approval all pass.

## Explicit non-goals

- No new candle/indicator engine.
- No attempt to infer Tabdeal's undocumented broadcast sequence behavior.
- No generic global sequence comparator.
- No automatic exchange selection or order submission.
- No promotion of ETH/SOL or non-crypto markets to strategy-approved scope.
