# SEQ-001..SEQ-016 Execution Evidence Ledger

- Reviewed source contract: `HES_Trade_Agent__Exchange_Sequence_Semantics_and_C.md`, scenario definitions SEQ-001..SEQ-016 (lines 210-225 in the supplied research file).
- Repository research note: [EXCHANGE_SEQUENCE_SEMANTICS_CROSS_VENUE_NOTE_2026-10-15.md](./EXCHANGE_SEQUENCE_SEMANTICS_CROSS_VENUE_NOTE_2026-10-15.md).
- Audited source commit: `58fba6549dfa135da23be83ed5accb24b8d6e44d`.
- Safety status: **HOLD / NO-TRADE**.
- Interpretation rule: a related test is not a pass unless its assertions cover the scenario's exact expected outcome. CI workflow success is not, by itself, proof that every scenario below was executed.

## CI evidence observed for audited commit

The following PR workflow runs were returned for the exact audited commit and their named jobs were checked as completed/success:
- [Controlled Forward Observation Runner v1 #671](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215436)
- [Forward Integration Verification v1 #677](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215471)
- [Clean Forward Evidence Verification v1 #675](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215524)
- [Signed Source Evidence Contract v1 #152](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215678)
- [Source Identity Reconciliation Lock v1 #732](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215587)
- [Local Durable Collector Safety v1 #653](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39132215222)

These establish workflow/job success on the audited commit; they do not establish that each of the 16 scenario-specific tests was run. The CI run listing also contained multiple unrelated successful workflows.

## Scenario ledger

| Scenario | Relevant test source found | Assessment | Status |
|---|---|---|---|
| SEQ-001 opaque repeated value with different payload | `tests/test_sequence_integrity_v1.py::test_opaque_repeated_sequence_with_different_payload_is_not_conflict` | Assertions directly cover the expected no-conflict behavior for unknown semantics. Per-test execution log not verified. | MAPPED / EXECUTION UNVERIFIED |
| SEQ-002 exact raw replay | `tests/test_sequence_integrity_v1.py::test_raw_payload_hash_exact_replay_is_idempotent`; transport exact-byte hash tests | Covers hash-match replay behavior; per-test execution log not verified. | MAPPED / EXECUTION UNVERIFIED |
| SEQ-003 conflicting documented trade identity | `test_verified_identity_mode_detects_conflicting_duplicate` and `tests/test_sequence_conflict_diagnostics_v1.py::test_conflicting_duplicate_reports_safe_field_diff_and_hashes` | Tests use verified sequence identity, not the scenario's exact documented `(venue, product, symbol, trade_id)` tuple. Not an exact match. | PARTIAL / BLOCKED |
| SEQ-004 missing sequence when registry marks it optional | `tests/test_tabdeal_readonly_adapter_v1.py::test_rejects_scope_and_incomplete`; `test_boolean_false_zero_and_missing_sequence_are_distinct_wire_cases` | Current Tabdeal adapter treats missing sequence as incomplete/rejected; the scenario requires behavior conditional on optional-vs-required registry policy. Registry-controlled optional-field case not established. | BLOCKED |
| SEQ-005 Binance Spot snapshot/range bootstrap | No exact scenario-specific test identified in inspected files. | Do not infer from general sequence tests. | BLOCKED |
| SEQ-006 Binance Spot gap and snapshot restart | No exact scenario-specific test identified in inspected files. | Do not infer from generic gap handling. | BLOCKED |
| SEQ-007 OKX equal seqId keepalive | No exact scenario-specific test identified in inspected files. | Venue-specific keepalive behavior remains unverified. | BLOCKED |
| SEQ-008 OKX maintenance sequence reset | No exact scenario-specific test identified in inspected files. | Venue-specific reset/re-baseline behavior remains unverified. | BLOCKED |
| SEQ-009 Bybit repeated Level 1 snapshot | No exact scenario-specific test identified in inspected files. | Venue-specific snapshot replacement remains unverified. | BLOCKED |
| SEQ-010 Bybit multiple trade messages sharing seq | No exact scenario-specific test identified in inspected files. | Per-trade identity behavior remains unverified. | BLOCKED |
| SEQ-011 Kraken book checksum mismatch | No exact scenario-specific test identified in inspected files. | CRC32/checksum invalidation remains unverified. | BLOCKED |
| SEQ-012 JSON false vs numeric zero vs missing | `tests/test_tabdeal_readonly_adapter_v1.py::test_boolean_false_zero_and_missing_sequence_are_distinct_wire_cases`; `test_rejects_boolean_float_and_non_ascii_sequence_wire_values` | Source assertions directly distinguish false, zero, and missing; per-test execution log not verified. | MAPPED / EXECUTION UNVERIFIED |
| SEQ-013 timestamp units and timezone offsets | `tests/test_tabdeal_readonly_adapter_v1.py::test_timestamp_units_and_offsets_normalize_to_same_utc`; `test_naive_timestamp_string_is_rejected` | Covers seconds/ms/µs/RFC3339/offset normalization and naive-time rejection; per-test execution log not verified. | MAPPED / EXECUTION UNVERIFIED |
| SEQ-014 reconnect creates a new sequence scope | `tests/test_sequence_integrity_v1.py::test_reconnect_resets_state`; `tests/test_sequence_candle_integration_v1.py::test_reconnect_does_not_compare_sequence_across_sessions` | Source assertions cover state reset/no cross-session comparison; per-test execution log not verified. | MAPPED / EXECUTION UNVERIFIED |
| SEQ-015 venue-documented snapshot reset | No exact snapshot-reset fixture/test identified in inspected files. | Reconnect reset is not a substitute for venue-specific lower-ID/snapshot reset. | BLOCKED |
| SEQ-016 corrupt checkpoint missing scope/invalid checksum | No exact test mapping verified in inspected files. | Recovery/idempotence tests are not accepted as equivalent without matching assertions. | BLOCKED |

## Required closure evidence

1. Add exact deterministic fixtures/tests for the blocked and partial scenarios, retaining venue-specific contracts rather than generic assumptions.
2. Obtain test-level execution evidence (exact SHA, workflow/run, job, test IDs/results) for every mapped scenario.
3. Verify Futures clock provenance from real captured evidence, not merely timestamp parser fixtures.
4. Verify exact raw received frame bytes and independently recompute SHA-256 against the pinned registry/evidence manifest.
5. Keep all promotion/trading gates closed until all required checks pass.
