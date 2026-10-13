import hashlib
import json
from datetime import datetime, timezone

from forward.controlled_forward_observation_runner_v1 import ControlledForwardObservationRunnerV1
from forward.observation_session_manager_v1 import ObservationSessionManagerV1
from forward.tabdeal_transport_v1 import TabdealReadOnlyTransportV1


class OneTradeWS:
    def __init__(self, url, on_open, on_message):
        self.on_open = on_open
        self.on_message = on_message

    def send(self, symbol):
        assert symbol == "BTC_USDT"

    def close(self):
        pass

    def run_forever(self, **kwargs):
        self.on_open(self)
        self.on_message(self, json.dumps({"trade": {
            "symbol": "BTC_USDT", "price": "65000.25", "amount": "0.01",
            "side_name": "buy", "sequence": "0007",
            "updated": "2026-10-13T00:00:00Z",
        }}, separators=(",", ":")))


def test_session_manager_creates_distinct_session_and_run_ids():
    manager = ObservationSessionManagerV1(policy_id="test", policy_version="1")
    session = manager.start(started_at=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
    assert session.session_id.startswith("SES-")
    assert session.run_id.startswith("OBS-")
    assert session.session_id != session.run_id
    assert session.record()["session_id"] == session.session_id
    assert session.record()["run_id"] == session.run_id


def test_transport_propagates_lifecycle_ids_and_exact_raw_frame_hash():
    output = []
    raw_message = json.dumps({"trade": {
        "symbol": "BTC_USDT", "price": "65000.25", "amount": "0.01",
        "side_name": "buy", "sequence": "0007",
        "updated": "2026-10-13T00:00:00Z",
    }}, separators=(",", ":"))

    class ExactFrameWS(OneTradeWS):
        def run_forever(self, **kwargs):
            self.on_open(self)
            self.on_message(self, raw_message)

    transport = TabdealReadOnlyTransportV1(
        as_of_provider=lambda: datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc),
        on_record=output.append,
        ws_factory=ExactFrameWS,
        session_id="SES-test",
        run_id="OBS-test",
    )
    transport.run_once()

    assert len(output) == 1
    assert output[0]["session_id"] == "SES-test"
    assert output[0]["run_id"] == "OBS-test"
    assert output[0]["sequence"] == "0007"
    assert output[0]["raw_payload"] == raw_message
    assert output[0]["raw_payload_sha256"] == hashlib.sha256(raw_message.encode()).hexdigest()


def test_runner_propagates_same_ids_to_fail_closed_consumer(tmp_path):
    session_path = tmp_path / "sessions.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=session_path,
        ws_factory=OneTradeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:contract",
    )
    result = runner.run(started_at=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
    session = json.loads(session_path.read_text().splitlines()[0])

    # Sequence semantics remain unknown, so the real consumer must block.
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_UNSAFE"
    assert result.session_id == session["session_id"]
    assert result.run_id == session["run_id"]
    assert result.diagnostics
    assert result.diagnostics[0]["session_id"] == session["session_id"]
    assert result.diagnostics[0]["run_id"] == session["run_id"]
    assert not (tmp_path / "observations.jsonl").exists()
