import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "forward" / "controlled_forward_observation_runner_contract_v1.json"
RUNNER = ROOT / "forward" / "controlled_forward_observation_runner_v1.py"


def test_runner_contract_requires_signed_sequence_contract_evidence():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["sequence_contract_verified_default"] is False
    assert contract["sequence_contract_envelope_required"] is True
    assert contract["sequence_contract_key_registry_required"] is True
    assert contract["expected_commit_required"] is True
    assert contract["expected_evidence_path_required"] is True
    assert contract["market_scope_required"] is True
    assert contract["signature_algorithm"] == "Ed25519"
    assert contract["block_reason"] == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert contract["block_before_network"] is True
    assert contract["block_before_session_write"] is True
    assert contract["fail_closed"] is True


def test_runner_source_contains_pre_network_signed_evidence_gate():
    source = RUNNER.read_text(encoding="utf-8")
    assert "sequence_contract_envelope_path" in source
    assert "sequence_contract_key_registry_path" in source
    assert "verify_sequence_contract_evidence(" in source
    assert "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED" in source
    assert "WS_FACTORY_REQUIRED" in source
