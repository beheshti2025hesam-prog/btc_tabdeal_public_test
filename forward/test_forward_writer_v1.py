from pathlib import Path
import tempfile

from forward.forward_writer_v1 import ForwardWriterV1


class FakeJournal:
    def __init__(self):
        self.records = []

    def append_decision(self, record):
        self.records.append(record)


def test_outcome_requires_existing_decision_when_checker_is_supplied():
    writer = ForwardWriterV1(FakeJournal())
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "outcome.json"
        try:
            writer.write_outcome_artifact(
                {"event_id": "missing", "outcome": "WIN"},
                path,
                decision_exists=lambda _: False,
            )
        except ValueError as exc:
            assert str(exc) == "outcome references unknown decision event_id"
        else:
            raise AssertionError("unknown decision event_id was accepted")


def test_outcome_artifact_is_exclusive_and_immutable():
    writer = ForwardWriterV1(FakeJournal())
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "outcome.json"
        record = {"event_id": "evt-1", "outcome": "WIN"}
        writer.write_outcome_artifact(record, path, decision_exists=lambda _: True)
        assert path.exists()
        try:
            writer.write_outcome_artifact(record, path, decision_exists=lambda _: True)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing outcome artifact was rewritten")
