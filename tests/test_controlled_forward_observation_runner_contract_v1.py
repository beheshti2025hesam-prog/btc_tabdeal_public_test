import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "forward" / "controlled_forward_observation_runner_contract_v1.json"
RUNNER = ROOT / "forward" / "controlled_forward_observation_runner_v1.py"


def test_runner_contract_requires_pinned_exact_scope_registry():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["sequence_registry_required"] is True
    assert contract["registry_sha256_pinned_in_code"] is True
    assert contract["tabdeal_broadcast_sequence_status"] == "UNKNOWN"
    assert contract["block_reason"] == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert contract["block_before_network"] is True
    assert contract["block_before_session_write"] is True
    assert contract["fail_closed"] is True


def test_runner_source_resolves_registry_before_transport_or_session():
    source = RUNNER.read_text(encoding="utf-8")
    assert "SequenceSemanticsRegistryV1.load_default()" in source
    assert "resolve_tabdeal_trade_sequence()" in source
    assert "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED" in source
    assert "sequence_contract_verified: bool" not in source
