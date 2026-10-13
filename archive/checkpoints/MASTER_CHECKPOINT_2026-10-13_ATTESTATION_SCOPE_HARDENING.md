# HES Trade Agent — Master Checkpoint: Attestation Scope Hardening
Date: 2026-10-13
Checkpoint: `ATTESTATION_SCOPE_HARDENING`
Disposition: `HOLD — COMBINED CI RE-RUN NOT YET CONFIRMED GREEN`

## Surgery performed
1. Read exact source-attestation verifier and test code on Draft PR #259 branch `fix/source-attestation-freshness-v1-20261012`.
2. Identified that the verifier checked only caller-supplied context keys. It did not require a complete scope tuple before verification.
3. Added required scope fields to the verifier:
   - venue
   - product
   - endpoint
   - channel
   - message_type
   - field
   - protocol_version
   - reviewed_commit_sha
   - contract_version
4. Added negative tests for incomplete expected scope and a mismatched reviewed commit.
5. Updated synthetic test fixtures to include the complete scope tuple and a fresh UTC timestamp; fixtures are explicitly synthetic and are not production evidence.

## Exact CI evidence
- First combined run: [Run 38381843151](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/38381843151)
- Head SHA: `483fecafac69c82564fe66fb43a9396a278754e4`
- Result: **48 passed, 1 failed**.
- Failure: `tests/test_independent_source_attestor_v1.py::test_signed_attestation_schema_is_compatible_with_verifier` used a fixed `2026-10-12T00:00:00Z` timestamp, which correctly failed the new 24-hour freshness gate during the 2026-10-13 CI run. Its synthetic context also omitted the now-required scope fields.
- Corrective test-fixture commit: `35e6e60d83f01d425c10f9135c18bab61fdeb936`.
- Follow-up workflow: [Run 38381981782](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/38381981782), exact head `35e6e60d83f01d425c10f9135c18bab61fdeb936`: **49 passed**. This confirmed the stale timestamp/scope fixture repair.

## Safety and scope
- Changes are confined to the Draft PR #259 branch; nothing was merged into `main`.
- No historical records, Winner selection, thresholds, evidence locks, VPS services, collector state, or trading state were changed.
- Test-generated keys and synthetic payloads are not a production trust root.
- Tabdeal inner `trade.sequence` semantics remain `unknown/opaque`; production evidence pin remains unset.
- No live collector, observation window, or trading is authorized.

## Additional adversarial validation
- Added a negative test where a validly re-signed synthetic attestation omits a required source-scope field; it must be rejected.
- Latest combined workflow: [Run 38382093737](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/38382093737), exact head `f9de4b2b1b471a4ee96ed4c77810b6ef44de58fd`: **50 passed in 0.27s**, job `registry-tests` succeeded.

## Next action
1. Review the exact final head and all call sites for complete expected source context; the current green CI proves these targeted tests, not production trust governance.
2. Keep PR #259 Draft and unmerged pending independent review, external trust-root governance, and authoritative Tabdeal sequence-contract evidence.
3. Do not repeat the 42-record reconciliation or infer sequence gaps from arithmetic alone.
