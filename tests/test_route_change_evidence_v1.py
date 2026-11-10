import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_route_change_evidence_v1 import load_contract, validate_record


def valid_record():
    contract = load_contract()
    record = {field: "fixture-value" for field in contract["evidence_record_required_fields"]}
    record.update({
        "source_contract_sha256": "a" * 64,
        "before_fixture_sha256": "b" * 64,
        "after_fixture_sha256": "c" * 64,
        "candidate_commit_sha": "d" * 40,
        "sequence_semantics_classification": "opaque_unknown",
        "scope_key_fields": ["venue", "product", "channel", "symbol", "session_id"],
        "tests_required": ["opaque_sequence_no_inferred_gap", "sequence_scope_isolation"],
        "ci_run_url": "https://github.com/example/repo/actions/runs/123",
        "ci_result": "success",
        "expected_behavior": "preserve_as_opaque_metadata",
    })
    return record


def test_complete_record_is_structurally_accepted_but_not_claimed_as_truth_verified():
    assert validate_record(valid_record(), load_contract()) == []


def test_missing_evidence_fields_fail_closed():
    record = valid_record()
    del record["source_contract_ref"]
    del record["after_fixture_sha256"]
    errors = validate_record(record, load_contract())
    assert "missing:source_contract_ref" in errors
    assert "missing:after_fixture_sha256" in errors


def test_malformed_hashes_and_commit_sha_are_rejected():
    record = valid_record()
    record["source_contract_sha256"] = "not-a-hash"
    record["candidate_commit_sha"] = "deadbeef"
    errors = validate_record(record, load_contract())
    assert "invalid_sha256:source_contract_sha256" in errors
    assert "invalid_commit_sha:candidate_commit_sha" in errors


def test_opaque_sequence_cannot_claim_gap_or_identity_conflict_from_value_alone():
    contract = load_contract()
    for unsafe in ("infer_gap_from_numeric_jump", "conflict_on_repeated_value"):
        record = valid_record()
        record["expected_behavior"] = unsafe
        assert "unsafe_inference_for_opaque_sequence" in validate_record(record, contract)


def test_ci_success_requires_an_https_run_url():
    record = valid_record()
    record["ci_run_url"] = "not-a-url"
    assert "success_requires_https_ci_run_url" in validate_record(record, load_contract())


def test_unknown_sequence_classification_is_rejected():
    record = valid_record()
    record["sequence_semantics_classification"] = "monotonic_because_numeric"
    assert "invalid:sequence_semantics_classification" in validate_record(record, load_contract())


def test_non_object_evidence_is_rejected():
    assert validate_record([], load_contract()) == ["record must be an object"]
