# HES Trade Agent — Sequence Integrity Review
Date: 2026-10-18 (+03:30)
Branch: research/binance-btcusdt-rest-schema-20261017
PR #308 latest head after hardening changes: 0ff9a4aaaec8225f3d05618144ffb72cb04d08be

## Scope
Static inspection of the sequence state machine, candle integration, observation path, controlled runner, diagnostic journal, collector and ingestion adapters, plus their tests and the source-identity workflow. Strict sequence parsing and regression tests have been committed on the research branch. CI/test execution for the latest head has not yet been returned by the GitHub connector; this is not an independent review.

## Confirmed from code
- Exact duplicate returns IDEMPOTENT_DUPLICATE.
- Same sequence with changed content returns REJECT_STREAM / CONFLICTING_DUPLICATE_SEQUENCE.
- Monotonic non-contiguous IDs are accepted; numeric jumps alone are not treated as proof of lost events.
- Lower sequence returns ANOMALY / OUT_OF_ORDER_SEQUENCE and does not move last_sequence backwards.
- The sequence parser was hardened to accept only non-negative Python integers or ASCII digit strings; bools, floats, non-finite values, whitespace-padded strings and malformed values are rejected. Equivalent strict parsing was applied at the Tabdeal collector and ingestion boundaries.
- Record-state bound rejects further unique records.
- Reconnect reset clears in-memory state without fabricating continuity.

## Open risks to verify
1. The state-machine class itself does not latch a persistent rejected state. However, the inspected SequenceAwareCandleIngestionV1 returns immediately on REJECT_STREAM/ANOMALY, ForwardObservationPathV1 maps this to BLOCKED/SEQUENCE_UNSAFE, and an existing controlled-runner test verifies a conflicting duplicate yields BLOCKED with no observation journal. A separate test should still prove that a bad event followed by later valid events in the same batch cannot leak data.
2. OUT_OF_ORDER_SEQUENCE is an ANOMALY, not a rejection. Prove such records cannot reach signal, risk, or decision inputs before reconciliation.
3. Strict parsing regression tests have been added for bool, fractional float, NaN/infinity, negative values, whitespace-padded strings and malformed numeric strings at the state-machine and ingestion layers, plus collector normalization tests. These are committed but not yet confirmed by a successful CI run.
4. The record map grows until reset and is bounded by count, not elapsed time. Verify safe rotation and explicit recovery.
5. Existing integration tests cover conflict blocking and diagnostic hash-chain corruption. Still missing or unverified: hash-valid but semantically invalid sequences, changed non-market fields, source deletion/reordering/tampering, protocol/order changes, and a follow-up valid record after a conflict in the same batch.
6. The source-identity workflow validates manifest values/counts/uniqueness and creates a SHA-256 lock over the manifest; it does not fetch and re-hash the original source blobs itself. Green CI is not equivalent to independent source-byte verification.

## Required adversarial cases
- Exact duplicate produces no second downstream decision.
- Same ID with changed market or non-market fields invalidates the stream according to an explicit policy.
- Out-of-order records cannot influence decisions before reconciliation.
- Numeric jumps remain diagnostic where contiguity is not guaranteed.
- Boolean, fractional, non-finite, and malformed sequence values are rejected without coercion.
- Hash-valid but semantically invalid record is rejected.
- Reconnect/replay records session boundaries and never invents continuity.
- Deletion, reordering, payload mutation, or manifest tampering fails verification.
- Protocol/order changes fail until contract and fixtures are deliberately updated.
- State-bound exhaustion follows an explicit fail-closed recovery path.

## Decision
Sequence integrity remains OPEN / NOT ACCEPTED. Inspect every caller of SequenceIntegrityV1.observe() and add focused regression tests before altering production behavior. Maintain HOLD / NO TRADE; this review does not authorize live collection or trading.
