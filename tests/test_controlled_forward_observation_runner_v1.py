import base64
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from scripts.verify_signed_source_evidence_v1 import canonical_signed_bytes

from forward.controlled_forward_observation_runner_v1 import (
    ControlledForwardObservationRunnerV1,
)


def signed_gate_kwargs(tmp_path: Path):
    """Build real synthetic Ed25519 evidence; never use a boolean as proof."""
    running_commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    private_key = Ed25519PrivateKey.generate()
    payload = b"Synthetic test fixture only; not production exchange evidence."
    source_url = "https://docs.tabdeal.org/"
    envelope = {
        "expected_commit": running_commit,
        "evidence_path": "evidence/sequence-contract.json",
        "raw_sha256": hashlib.sha256(payload).hexdigest(),
        "source_url": source_url,
        "redirect_chain": [source_url],
        "retrieved_at": "2026-10-07T13:00:00+00:00",
        "market_scope": "tabdeal:futures:BTC_USDT",
        "key_id": "synthetic-test-key",
        "signature_algorithm": "Ed25519",
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "sequence_contract": {
            "schema": "hes_sequence_contract_attestation_v1",
            "status": "verified",
            "market_scope": "tabdeal:futures:BTC_USDT",
            "venue": "tabdeal",
            "product": "fapi-futures-margin",
            "symbol": "BTC_USDT",
            "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
            "channel_or_topic": "BTC_USDT raw-text subscription",
            "message_type": "trade-envelope",
            "field_path": "trade.sequence",
            "protocol_version": "synthetic-test-protocol-v1",
            "semantic_class": "message_sequence",
            "capabilities": {
                "unique": True, "ordered": True, "contiguous": True,
                "comparable_across_reconnect": False,
            },
            "source_evidence": {
                "source_kind": "primary",
                "source_url": "https://docs.tabdeal.org/",
                "retrieved_at": "2026-10-07T13:00:00+00:00",
                "source_snapshot_sha256": hashlib.sha256(payload).hexdigest(),
                "evidence_excerpt": payload.decode("utf-8"),
            },
        },
    }
    envelope["signature_b64"] = base64.b64encode(
        private_key.sign(canonical_signed_bytes(envelope))
    ).decode("ascii")
    public_key = base64.b64encode(
        private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    envelope_path = tmp_path / "signed-sequence-contract.json"
    registry_path = tmp_path / "trusted-test-keys.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    registry_path.write_text(json.dumps({"synthetic-test-key": public_key}), encoding="utf-8")
    # In production this value is supplied by protected deployment configuration;
    # the test pins the exact synthetic registry bytes independently of the envelope.
    os.environ["HES_TRUSTED_KEY_REGISTRY_SHA256"] = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    return {
        "sequence_contract_envelope_path": envelope_path,
        "sequence_contract_key_registry_path": registry_path,
        "expected_commit": running_commit,
        "expected_evidence_path": "evidence/sequence-contract.json",
        "market_scope": "tabdeal:futures:BTC_USDT",
        "evidence_max_age_seconds": 3600,
    }


class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message

    def run_forever(self, **kwargs):
        self.on_open(self)
        for seq, price in ((100, "100.0"), (101, "101.0"), (102, "102.0")):
            self.on_message(self, '{"trade": {"symbol":"BTC_USDT","price":"%s","amount":"0.1","side":"buy","sequence":%d,"updated":"2026-10-07T13:00:00Z"}}' % (price, seq))

    def send(self, symbol):
        assert symbol == "BTC_USDT"

    def close(self):
        pass


def test_runner_uses_transport_and_writes_observation(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "WAITING"
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert session.exists()
    session_record = json.loads(session.read_text(encoding="utf-8").splitlines()[0])
    evidence = session_record["sequence_contract_evidence"]
    assert evidence["status"] == "VERIFIED"
    assert evidence["sequence_contract_schema"] == "hes_sequence_contract_attestation_v1"
    assert evidence["sequence_contract_semantic_class"] == "message_sequence"
    assert json.loads(evidence["sequence_contract_capabilities_json"]) == {
        "unique": True, "ordered": True, "contiguous": True,
        "comparable_across_reconnect": False,
    }
    assert evidence["source_snapshot_sha256"] == "a" * 64
    assert evidence["expected_commit"] == subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    assert evidence["evidence_path"] == "evidence/sequence-contract.json"
    assert evidence["market_scope"] == "tabdeal:futures:BTC_USDT"
    assert evidence["key_id"] == "synthetic-test-key"
    assert len(evidence["raw_sha256"]) == 64
    assert len(evidence["envelope_sha256"]) == 64
    assert len(evidence["key_registry_sha256"]) == 64
    assert session_record["session_digest"]
    assert not journal.exists()


def test_runner_accepts_non_contiguous_monotonic_sequence(tmp_path: Path):
    class GapTransport:
        def __init__(self, on_record, **kwargs):
            self.on_record = on_record

        def run_once(self):
            for seq in (100, 102):
                self.on_record({"symbol":"BTC_USDT","price":"100","amount":"0.1","side":"buy",
                                "sequence":seq,"timestamp":"2026-10-07T13:00:00Z"})

    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        transport_factory=GapTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "WAITING"
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert not (tmp_path / "journal.jsonl").exists()


def test_runner_does_not_write_when_transport_has_no_records(tmp_path: Path):
    class EmptyWS(FakeWS):
        def run_forever(self, **kwargs):
            self.on_open(self)

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        ws_factory=EmptyWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "WAITING"
    assert result.reason == "NO_FRESH_RECORDS"
    assert not journal.exists()


def test_runner_fails_closed_on_transport_error(tmp_path: Path):
    class BrokenTransport:
        def __init__(self, **kwargs):
            pass

        def run_once(self):
            raise RuntimeError("simulated transport failure")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=BrokenTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_ERROR:RuntimeError"
    assert result.records_received == 0
    assert session.exists()
    assert not journal.exists()


def test_runner_fails_closed_on_transport_construction_error(tmp_path: Path):
    class BrokenTransport:
        def __init__(self, **kwargs):
            raise RuntimeError("simulated construction failure")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=BrokenTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_ERROR:RuntimeError"
    assert result.records_received == 0
    assert session.exists()
    assert not journal.exists()


def test_runner_fails_closed_when_record_bound_is_exceeded(tmp_path: Path):
    class OverLimitTransport:
        def __init__(self, on_record, **kwargs):
            self.on_record = on_record

        def run_once(self):
            for seq in range(4):
                self.on_record({"symbol":"BTC_USDT","price":"100","amount":"0.1","side":"buy",
                                "sequence":seq,"timestamp":"2026-10-07T13:00:00Z"})

    journal = tmp_path / "journal.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=tmp_path / "session.jsonl",
        transport_factory=OverLimitTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **signed_gate_kwargs(tmp_path),
        max_records=3,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "FORWARD_RECORD_BOUND_EXCEEDED"
    assert result.records_received == 3
    assert result.diagnostics == ({"max_records": 3},)
    assert not journal.exists()


def test_runner_blocks_before_network_or_session_without_verified_sequence_contract(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed before sequence contract verification")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason.startswith("UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED")
    assert result.run_id == "NOT_STARTED"
    assert result.records_received == 0
    assert result.diagnostics == ({
        "network_started": False,
        "session_written": False,
        "signature_verified": False,
        "sequence_contract_evidence_required": True,
        "verification_error": "ValueError",
    },)
    assert not session.exists()
    assert not journal.exists()


def test_runner_blocks_missing_ws_factory_before_session_or_transport(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed without ws_factory")

    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=session,
        transport_factory=MustNotRunTransport,
        **signed_gate_kwargs(tmp_path),
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "WS_FACTORY_REQUIRED"
    assert result.run_id == "NOT_STARTED"
    assert result.diagnostics == ({
        "network_started": False,
        "session_written": False,
        "signature_verified": True,
        "ws_factory_required": True,
    },)
    assert not session.exists()
    assert not (tmp_path / "journal.jsonl").exists()


def test_runner_blocks_coordinated_registry_and_envelope_replacement(tmp_path: Path):
    """A new attacker key plus a re-signed envelope cannot replace the pinned registry."""
    kwargs = signed_gate_kwargs(tmp_path)
    envelope_path = kwargs["sequence_contract_envelope_path"]
    registry_path = kwargs["sequence_contract_key_registry_path"]

    attacker_key = Ed25519PrivateKey.generate()
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["key_id"] = "attacker-controlled-key"
    envelope.pop("signature_b64", None)
    envelope["signature_b64"] = base64.b64encode(
        attacker_key.sign(canonical_signed_bytes(envelope))
    ).decode("ascii")
    attacker_public_key = base64.b64encode(
        attacker_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    # Replace both files, but deliberately leave the deployment-pinned digest unchanged.
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    registry_path.write_text(json.dumps({"attacker-controlled-key": attacker_public_key}), encoding="utf-8")

    session = tmp_path / "session.jsonl"
    journal = tmp_path / "journal.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **kwargs,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.run_id == "NOT_STARTED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED:ValueError"
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not session.exists()
    assert not journal.exists()


def test_runner_blocks_when_signed_evidence_is_not_configured(tmp_path: Path):
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        ws_factory=FakeWS,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason.startswith("UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED")
    assert not (tmp_path / "session.jsonl").exists()


def test_runner_rejects_signed_evidence_for_a_different_running_commit(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed for another commit")

    kwargs = signed_gate_kwargs(tmp_path)
    kwargs["expected_commit"] = "f" * 40
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        **kwargs,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.run_id == "NOT_STARTED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED:ValueError"
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not session.exists()
    assert not (tmp_path / "journal.jsonl").exists()
