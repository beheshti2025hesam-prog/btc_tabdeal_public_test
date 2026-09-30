"""Regression coverage for the sample-level outcome/embargo audit."""
from pathlib import Path


def test_outcome_timestamp_audit_declares_locked_boundary():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "outcome_timestamp_embargo_boundary_audit.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"' in source
    assert "CROSS_BOUNDARY_OUTCOME" in source
    assert "minimum_embargo_observations" in source
    assert "historical_protocol_modified" in source
