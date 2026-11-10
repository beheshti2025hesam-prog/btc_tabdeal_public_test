"""Fail-closed validation for route-change evidence records (no network access)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "evidence" / "route_change_evidence_contract_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_record(record: Any, contract: dict[str, Any]) -> list[str]:
    """Return validation errors; empty means structurally complete, not truth-verified."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record must be an object"]

    for field in contract["evidence_record_required_fields"]:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing:{field}")

    for field in ("source_contract_sha256", "before_fixture_sha256", "after_fixture_sha256"):
        value = record.get(field)
        if value is not None and (not isinstance(value, str) or not SHA256_RE.fullmatch(value)):
            errors.append(f"invalid_sha256:{field}")

    commit = record.get("candidate_commit_sha")
    if commit is not None and (not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit)):
        errors.append("invalid_commit_sha:candidate_commit_sha")

    classification = record.get("sequence_semantics_classification")
    if classification is not None and classification not in contract["sequence_semantics_allowed"]:
        errors.append("invalid:sequence_semantics_classification")

    tests = record.get("tests_required")
    if tests is not None and (not isinstance(tests, list) or not tests or
                              any(not isinstance(item, str) or not item.strip() for item in tests)):
        errors.append("invalid:tests_required")

    if record.get("ci_result") not in (None, "success", "failure", "cancelled", "unknown"):
        errors.append("invalid:ci_result")
    if record.get("ci_result") == "success":
        url = record.get("ci_run_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            errors.append("success_requires_https_ci_run_url")
    if classification == "opaque_unknown" and record.get("expected_behavior") in (
        "infer_gap_from_numeric_jump", "conflict_on_repeated_value"
    ):
        errors.append("unsafe_inference_for_opaque_sequence")

    return errors


def load_contract() -> dict[str, Any]:
    import json
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
