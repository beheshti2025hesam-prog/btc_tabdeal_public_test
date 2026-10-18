# SEQ-001..SEQ-016 Execution Evidence Ledger

- Audit target commit: `b9044f770887d5e1e9d67d4b5c05c5bdc7585af8`
- Audit scope: test-source mapping only; this file does not claim tests were executed.
- Safety status: HOLD / NO-TRADE.
- Important limitation: the current PR changed-file list and the inspected sequence test files do not contain explicit `SEQ-001` ... `SEQ-016` identifiers. Therefore an exact ID-to-test mapping cannot be honestly asserted from the evidence inspected. Do not mark a scenario PASS merely because a related general test exists.

## Existing relevant test functions observed at the audit target

### `tests/test_sequence_integrity_v1.py`
- `test_unknown_sequence_semantics_accepts_first_value_without_claiming_order`
- `test_opaque_repeated_sequence_with_different_payload_is_not_conflict`
- `test_opaque_backward_sequence_is_not_ordering_anomaly`
- `test_raw_payload_hash_exact_replay_is_idempotent`
- `test_different_raw_payload_hash_same_sequence_is_not_conflict`
- `test_verified_identity_mode_detects_conflicting_duplicate`
- `test_verified_ordering_mode_detects_regression`
- `test_exact_normalized_duplicate_only_deduped_in_verified_mode`
- `test_reconnect_resets_state`
- `test_invalid_sequence_fails_closed`
- `test_invalid_sequence_wire_types_reject_without_state_mutation`
- `test_only_nonnegative_int_and_ascii_digit_strings_are_valid`
- `test_unique_sequence_state_bound_fails_closed_without_growth`

### `tests/test_sequence_candle_integration_v1.py`
- `test_clean_timestamps_reach_closed_candle_without_sequence_claims`
- `test_exact_duplicate_without_raw_digest_is_not_silently_deduplicated`
- `test_same_timestamp_conflicting_prices_block_candle_formation`
- `test_non_contiguous_sequence_is_accepted_without_gap_inference`
- `test_signed_ordering_capability_is_explicitly_required_for_timestamp_ties`
- `test_ordering_capability_does_not_imply_duplicate_identity`
- `test_reconnect_does_not_compare_sequence_across_sessions`

### `tests/test_tabdeal_readonly_adapter_v1.py`
- Contains a targeted test distinguishing JSON `false`, numeric `0`, and a missing sequence field. This is test-source presence only until the exact target-commit CI/job output confirms execution.

### `tests/test_tabdeal_transport_v1.py`
- Contains tests for hashing exact received raw-frame bytes and for formatting-sensitive raw payload hashes. This is test-source presence only until the exact target-commit CI/job output confirms execution.

## Scenario ledger

Each row remains `UNMAPPED` until the authoritative scenario definition is recovered and linked to a concrete test function, exact commit, and successful execution evidence.

| Scenario | Test mapping | Execution evidence | Status |
|---|---|---|---|
| SEQ-001 | UNMAPPED | Not established | BLOCKED |
| SEQ-002 | UNMAPPED | Not established | BLOCKED |
| SEQ-003 | UNMAPPED | Not established | BLOCKED |
| SEQ-004 | UNMAPPED | Not established | BLOCKED |
| SEQ-005 | UNMAPPED | Not established | BLOCKED |
| SEQ-006 | UNMAPPED | Not established | BLOCKED |
| SEQ-007 | UNMAPPED | Not established | BLOCKED |
| SEQ-008 | UNMAPPED | Not established | BLOCKED |
| SEQ-009 | UNMAPPED | Not established | BLOCKED |
| SEQ-010 | UNMAPPED | Not established | BLOCKED |
| SEQ-011 | UNMAPPED | Not established | BLOCKED |
| SEQ-012 | UNMAPPED | Not established | BLOCKED |
| SEQ-013 | UNMAPPED | Not established | BLOCKED |
| SEQ-014 | UNMAPPED | Not established | BLOCKED |
| SEQ-015 | UNMAPPED | Not established | BLOCKED |
| SEQ-016 | UNMAPPED | Not established | BLOCKED |

## Required closure evidence

1. Recover the authoritative definitions and expected outcomes for SEQ-001..SEQ-016.
2. Link every scenario to a concrete executable test (no inferred mapping).
3. Run the targeted tests and record the exact commit SHA, workflow run, job, and result.
4. Independently validate Futures clock provenance, raw-frame byte capture, and recomputed SHA-256 against the pinned registry.
5. Keep all promotion/trading gates closed until all required checks pass.
