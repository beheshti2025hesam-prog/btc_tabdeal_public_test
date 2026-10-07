from datetime import datetime, timezone
from pathlib import Path

from forward.controlled_forward_observation_runner_v1 import (
    ControlledForwardObservationRunnerV1,
)


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
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "WAITING"
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert session.exists()
    assert not journal.exists()


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
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_ERROR:RuntimeError"
    assert result.records_received == 0
    assert session.exists()
    assert not journal.exists()
