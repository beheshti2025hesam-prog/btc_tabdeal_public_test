# HES Trade Agent — Sequence Integrity Review
Date: 2026-10-18 (+03:30)
Branch: research/binance-btcusdt-rest-schema-20261017
PR #308 head reviewed: 0b286f776d6ab75c619f38ee737fde4940473d93

## Scope
Static inspection only: forward/sequence_integrity_v1.py, tests/test_sequence_integrity_v1.py, and .github/workflows/source-identity-reconciliation-lock-v1.yml. This is not an executed test suite or independent review.

## Confirmed from code
- Exact duplicate returns IDEMPOTENT_DUPLICATE.
- Same sequence with changed content returns REJECT_STREAM / CONFLICTING_DUPLICATE_SEQUENCE.
- Monotonic non-contiguous IDs are accepted; numeric jumps alone are not treated as proof of lost events.
- Lower sequence returns ANOMALY / OUT_OF_ORDER_SEQUENCE and does not move last_sequence backwards.
- Invalid values that int(value) cannot parse raise ValueError.
- Record-state bound rejects further unique records.
- Reconnect reset clears in-memory state without fabricating continuity.

## Open risks to verify
1. REJECT_STREAM is returned as an event, but this class does not latch a persistent rejected state. Prove every caller stops/invalidates the stream after a conflict; otherwise later records may still be accepted.
2. OUT_OF_ORDER_SEQUENCE is an ANOMALY, not a rejection. Prove such records cannot reach signal, risk, or decision inputs before reconciliation.
3. int(value) can coerce bools and fractional floats to integers. Test True, 1.9, non-finite values, and malformed strings; define allowed source representations before changing behavior.
4. The record map grows until reset and is bounded by count, not elapsed time. Verify safe rotation and explicit recovery.
5. The inspected unit test file has eight basic tests but does not cover downstream veto propagation, hash-valid semantically invalid sequences, changed non-market fields, deletion/tampering, or protocol/order changes.
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
