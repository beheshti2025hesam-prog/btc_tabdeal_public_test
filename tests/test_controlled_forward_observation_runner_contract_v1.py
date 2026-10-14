import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "forward" / "controlled_forward_observation_runner_contract_v1.json"
RUNNER = ROOT / "forward" / "controlled_forward_observation_runner_v1.py"


def test_runner_contract_requires_authoritative_sequence_contract_evidence():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["sequence_contract_verified_default"] is False
    assert contract["sequence_contract_evidence_ref_required"] is True
    assert contract["sequence_contract_evidence_ref_must_match_reviewed_pin"] is True
    assert contract["reviewed_sequence_contract_evidence_ref"] is None
    assert contract["block_reason"] == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert contract["block_before_network"] is True
    assert contract["block_before_session_write"] is True
    assert contract["fail_closed"] is True


def test_runner_source_contains_pre_network_sequence_contract_block():
    source = RUNNER.read_text(encoding="utf-8")
    assert "sequence_contract_verified: bool = False" in source
    assert "sequence_contract_evidence_ref" in source
    assert "VERIFIED_UPSTREAM_SEQUENCE_CONTRACT_EVIDENCE_REF: str | None = None" in source
    assert "sequence_contract_evidence_ref == approved_ref" in source
    assert "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED" in source