import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"forward"/"controlled_forward_observation_runner_contract_v1.json"
RUNNER=ROOT/"forward"/"controlled_forward_observation_runner_v1.py"

def test_runner_contract_requires_exact_scope_capability_registry():
    contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["sequence_contract_verified_default"] is False
    assert contract["sequence_contract_evidence_ref_required"] is True
    assert contract["sequence_capability_registry"]=="docs/protocol/sequence_semantics_registry_v1.json"
    assert contract["sequence_capabilities_required"]==[
        "event_identity_unique","ordered_within_scope","contiguous_within_scope","gap_detectable"]
    assert contract["block_reason"]=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert contract["block_before_network"] is True
    assert contract["block_before_session_write"] is True
    assert contract["caller_boolean_override_allowed"] is False
    assert contract["fail_closed"] is True

def test_runner_source_uses_registry_and_has_no_caller_boolean_override():
    source=RUNNER.read_text(encoding="utf-8")
    assert "evaluate_tabdeal_trade_sequence_capabilities" in source
    assert "sequence_contract_verified: bool" not in source
    assert "UPSTREAM_SEQUENCE_CAPABILITIES_UNVERIFIED" not in source
