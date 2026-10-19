import hashlib
import json
from datetime import datetime, timezone

import pytest

from forward.wallex_controlled_observation_runner_v1 import run_bounded_observation


class FakeSocket:
    def __init__(self, sid, channel):
        self.sid = sid
        self.channel = channel
        self.sent = []
        self.closed = False
        self.delivered = False
        self.timeout = None

    def recv(self):
        if self.sid is not None:
            sid, self.sid = self.sid, None
            return json.dumps({"sid": sid, "upgrades": [], "pingInterval": 20000,
                               "pingTimeout": 30000, "maxPayload": 1048576})
        if not self.delivered:
            self.delivered = True
            return json.dumps([self.channel, [{"price": 10, "quantity": 1, "sum": 10}]])
        raise TimeoutError("fake receive timeout")

    def send(self, payload):
        self.sent.append(payload)

    def settimeout(self, timeout):
        self.timeout = timeout

    def close(self):
        self.closed = True


def test_bounded_runner_pins_evidence_and_rejects_stale_epoch(tmp_path):
    sockets = [
        FakeSocket("sid-1", "BTCUSDT@buyDepth"),
        FakeSocket("sid-2", "BTCUSDT@buyDepth"),
    ]
    out = tmp_path / "capture.jsonl"
    result = run_bounded_observation(
        output_jsonl=out,
        symbol="BTCUSDT",
        channels=("buyDepth",),
        session_seconds=0.01,
        session_count=2,
        socket_factory=lambda endpoint, timeout: sockets.pop(0),
        clock=lambda: datetime(2026, 10, 18, tzinfo=timezone.utc),
        monotonic_ns=lambda: 42,
    )
    assert result["server_session_ids_distinct"]
    assert result["total_accepted_events"] == 2
    assert result["all_stale_injections_rejected"]
    assert result["stale_frame_injections"][0]["source"] == "captured_prior_session_frame"
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["raw_sha256"] == hashlib.sha256(row["raw"].encode()).hexdigest() for row in rows)
    sidecar = out.with_name(out.name + ".sha256").read_text()
    assert hashlib.sha256(out.read_bytes()).hexdigest() in sidecar
    manifest_path = tmp_path / "capture.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["runtime_activated"] is False
    assert manifest["orders_sent"] is False


@pytest.mark.parametrize("kwargs", [
    {"session_seconds": 0},
    {"session_seconds": 301},
    {"session_count": 1},
    {"session_count": 6},
])
def test_bounded_runner_rejects_unsafe_bounds(tmp_path, kwargs):
    args = {"output_jsonl": tmp_path / "capture.jsonl", "session_seconds": 0.01, "session_count": 2}
    args.update(kwargs)
    with pytest.raises(ValueError):
        run_bounded_observation(**args)


def test_bounded_runner_refuses_to_overwrite_existing_evidence(tmp_path):
    out = tmp_path / "capture.jsonl"
    out.write_text("keep\n")
    with pytest.raises(FileExistsError):
        run_bounded_observation(output_jsonl=out, session_seconds=0.01, session_count=2)


def test_bounded_runner_refuses_to_overwrite_existing_manifest(tmp_path):
    manifest = tmp_path / "capture.manifest.json"
    manifest.write_text("preserve\n")
    with pytest.raises(FileExistsError):
        run_bounded_observation(output_jsonl=tmp_path / "capture.jsonl", session_seconds=0.01, session_count=2)
    assert manifest.read_text() == "preserve\n"
