from datetime import datetime, timezone
from forward.observation_snapshot_identity_v1 import ObservationSnapshotIdentityV1
from forward.observation_journal_v1 import ObservationJournalV1


def make():
    return ObservationSnapshotIdentityV1().create(
        forward_run_id="RUN-1",
        observed_at=datetime(2026,10,7,12,0,tzinfo=timezone.utc),
        symbol="BTC_USDT", timeframe="15m", payload={"regime":"UPTREND","quality":"HIGH"})


def test_append_and_read(tmp_path):
    j=ObservationJournalV1(tmp_path/"observations.jsonl")
    s=make()
    j.append(s)
    assert j.read()==[s]


def test_append_is_immutable_identity(tmp_path):
    j=ObservationJournalV1(tmp_path/"observations.jsonl")
    s=make()
    j.append(s); j.append(s)
    assert j.read()==[s,s]


def test_missing_journal_is_empty(tmp_path):
    assert ObservationJournalV1(tmp_path/"missing.jsonl").read()==[]
