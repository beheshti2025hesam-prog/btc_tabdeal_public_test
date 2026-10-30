# Exchange event identity and sequence policy v1

## Purpose

Prevent a future venue adapter from treating a numeric field named `sequence`, `seq`, `id`, `tradeId`, `u`, or `updateId` as a universal ordering or gap contract. This policy is deliberately narrower than an exchange abstraction: every capability is scoped to the exact venue, product, endpoint, channel, message type, field path, symbol, timeframe, and session.

## Active HES Gate.io market-data contract

The current HES collector consumes **Gate.io Public Spot candlesticks only**. It does not consume trade IDs or order-book update IDs.

- REST endpoint: `GET /api/v4/spot/candlesticks`
- WebSocket channel: `spot.candlesticks`, event `update`
- Exact WebSocket instrument identity: `result.n = <interval>_<currency_pair>` (for example `15m_BTC_USDT`). An interval-only or mismatched symbol value is rejected.
- REST candle row contract: `[timestamp, quote_volume, close, high, low, open, base_volume]`; HES stores `volume=base_volume` and `quote_volume=quote_volume` without swapping them.
- REST candle timestamp: row index 0, Unix seconds.
- WebSocket candle timestamp: `result.t`, Unix seconds.
- HES candle identity: `(source, product=spot, symbol, timeframe, open_time)`.
- For a known fixed interval, HES checks expected candle-open-time cadence. This is **candle-series gap detection**, not a trade-stream or order-book sequence detector.
- Candle timestamps are absolute epoch times and can deduplicate the same candle across reconnects only within the same exact source/product/symbol/timeframe scope. Never compare them with trade IDs, order-book IDs, another product, or another venue.
- Persisted rows must carry the canonical `hes_global_candle_v1` schema and both base/quote volume fields; OHLC and timestamp alignment are validated.
- A conflicting payload for the same candle identity is rejected; an exact semantic replay is idempotent. Missing historical candles returned by REST are merged by timestamp into a sorted, atomically replaced JSONL file under an exclusive per-feed lock.

Official Gate.io Spot API documentation specifies that `GET /spot/candlesticks` returns Unix-second candle timestamps, the OHLCV field order, supported intervals, and a maximum of 1,000 points per query. Source: https://www.gate.com/docs/developers/apiv4/en/spot/

## Reuse boundary with existing sequence contracts

The repository already has `forward/sequence_integrity_contract_v1.json`, `forward/sequence_integrity_v1.py`, and `forward/sequence_candle_integration_contract_v1.json`. Those existing contracts govern the prior forward **trade-observation sequence** path. They are not a generic sequence specification for every market-data product and must not be applied to Gate.io candle timestamps.

This Gate.io Spot candle path has no trade/order-book sequence field. It uses the exact candle-open-time identity described above. The existing trade-sequence state machine is not copied, forked, or inserted into this candle reader; the two paths remain explicitly separate.

## Unknown by default for every other adapter

No other venue/product/channel has an active HES sequence capability in this release. A future adapter must add a separately reviewed, append-only evidence record before it can use any sequence-like field for:
- event identity or deduplication;
- ordered comparison;
- contiguous gap detection;
- snapshot/delta synchronization;
- reconnect/session comparison;
- conflict classification.

Unknown means all of those capabilities are false. Numeric shape, apparent monotonicity in a short capture, or a field name is not evidence. A live capture is observational evidence only and cannot silently upgrade an unknown guarantee.

## Required evidence record

Every future record must bind:
1. venue, product, exact endpoint/channel/message type and protocol version;
2. exact field path and semantic class (`opaque_metadata`, `event_identity`, `ordered_sequence`, or `book_update_range`);
3. uniqueness, order, contiguity, scope key, session/reconnect behavior, duplicate/reset behavior, and snapshot bootstrap rules;
4. official source URL, retrieved-at timestamp, source content hash, minimal raw fixture, and verification status;
5. deterministic replay/property tests for duplicates, conflicting reuse, gaps, reconnect, reset, malformed payload, and schema drift.

A registry revision is immutable. Changes create a new revision; stale or conflicting evidence degrades the affected adapter to observation-only / NO_TRADE. No global sequence comparator is permitted.

## Release boundary

Gate.io remains the canonical chart/analysis provider for the current crypto Spot scope. An execution venue is a separate adapter and must never supply a second candle/volume source to the analysis engine. No live execution is authorized by this document.


## Bounded live-read policy

The append-only JSONL history is preserved in full. The live collector's normal duplicate-check/merge path and the dashboard reader inspect only the newest 5,000 rows per exact symbol/timeframe. This bounds steady-state memory, disk I/O, and reader latency without deleting history. The reader requires at least 200 closed candles; the 5,000-row window leaves a large safety margin. Only a rare historical gap repair loads and atomically rewrites the full file to keep it chronologically ordered.
