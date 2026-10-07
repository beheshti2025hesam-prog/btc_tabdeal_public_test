from datetime import datetime, timezone
import pytest
from forward.observation_journal_integration_v1 import ObservationJournalIntegrationV1
from forward.observation_journal_v1 import ObservationJournalV1

def test_quality_to_snapshot_to_journal(tmp_path):
    j=ObservationJournalV1(tmp_path/"journal.jsonl")
    i=ObservationJournalIntegrationV1(j)
    report,s=i.record(forward_run_id="RUN-1",
        observed_at=datetime(2026,10,7,12,0,tzinfo=timezone.utc),
        regime="UPTREND",quality="HIGH",gate_safe=True)
    assert report.report_state=="OBSERVATION_QUALIFIED"
    assert j.read()==[s]

def test_duplicate_snapshot_rejected(tmp_path):
    j=ObservationJournalV1(tmp_path/"journal.jsonl")
    i=ObservationJournalIntegrationV1(j)
    kwargs=dict(forward_run_id="RUN-1",
        observed_at=datetime(2026,10,7,12,0,tzinfo=timezone.utc),
        regime="UPTREND",quality="HIGH",gate_safe=True)
    i.record(**kwargs)
    with pytest.raises(ValueError,match="duplicate snapshot identity"):
        i.record(**kwargs)

def test_observation_payload_is_persisted(tmp_path):
    j=ObservationJournalV1(tmp_path/"journal.jsonl")
    i=ObservationJournalIntegrationV1(j)
    _,s=i.record(forward_run_id="RUN-2",
        observed_at=datetime(2026,10,7,12,1,tzinfo=timezone.utc),
        regime="DOWNTREND",quality="HIGH",gate_safe=True,
        observation_payload={"structure":"DOWN_CONTEXT"})
    assert s.digest
    assert j.read()[0].digest==s.digest
