from datetime import datetime, timezone
from pathlib import Path
import pytest
from forward.controlled_forward_observation_runner_v1 import ControlledForwardObservationRunnerV1

def test_runner_blocks_before_network_or_session_write_when_capabilities_unknown(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self,**kwargs):
            raise AssertionError("transport must not be constructed while capabilities are unknown")
    journal=tmp_path/"journal.jsonl"; session=tmp_path/"session.jsonl"
    runner=ControlledForwardObservationRunnerV1(
        journal_path=journal,session_path=session,transport_factory=MustNotRunTransport,
        ws_factory=lambda *args,**kwargs:None,max_runtime_seconds=1)
    result=runner.run(started_at=datetime(2026,10,7,13,1,tzinfo=timezone.utc))
    assert result.status=="BLOCKED"
    assert result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.run_id=="NOT_STARTED" and result.records_received==0
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert result.diagnostics[0]["capability_gate"]["capabilities"]["event_identity_unique"]=="unknown"
    assert not session.exists() and not journal.exists()

def test_legacy_boolean_override_is_not_an_accepted_runner_argument(tmp_path: Path):
    with pytest.raises(TypeError):
        ControlledForwardObservationRunnerV1(
            journal_path=tmp_path/"journal.jsonl",session_path=tmp_path/"session.jsonl",
            sequence_contract_verified=True,
            sequence_contract_evidence_ref="arbitrary-string-is-not-evidence")
