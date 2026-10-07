from datetime import datetime, timezone, timedelta
from forward.forward_observation_path_v1 import ForwardObservationPathV1

def frame(seq, when, price):
    return {"type":"trade","symbol":"BTC_USDT","price":str(price),"amount":"0.01",
            "side":"buy","sequence":seq,"timestamp":when.isoformat()}

def test_full_forward_observation_path(tmp_path):
    as_of=datetime(2026,10,7,12,31,tzinfo=timezone.utc)
    frames=[frame(1,as_of-timedelta(minutes=30),100),
            frame(2,as_of-timedelta(minutes=25),101),
            frame(3,as_of-timedelta(minutes=15),102),
            frame(4,as_of-timedelta(minutes=10),104)]
    result=ForwardObservationPathV1(tmp_path/"observations.jsonl").observe(
        frames,as_of=as_of,forward_run_id="OBS-E2E-001")
    assert result.status=="OBSERVED"
    assert result.frames_accepted==4
    assert result.candles==2
    assert result.structure_bias=="UP_CONTEXT"
    assert result.regime=="UPTREND"
    assert result.quality=="HIGH"
    assert result.gate_safe is True
    assert result.snapshot_id
    assert len(ForwardObservationPathV1(tmp_path/"observations.jsonl").journal.read())==1

def test_sequence_gap_blocks_before_structure(tmp_path):
    as_of=datetime(2026,10,7,12,31,tzinfo=timezone.utc)
    frames=[frame(1,as_of-timedelta(minutes=30),100),
            frame(3,as_of-timedelta(minutes=25),101)]
    result=ForwardObservationPathV1(tmp_path/"observations.jsonl").observe(
        frames,as_of=as_of,forward_run_id="OBS-E2E-GAP")
    assert result.status=="BLOCKED"
    assert result.reason=="SEQUENCE_UNSAFE"
    assert result.diagnostics == (
        {"sequence": 1, "status": "ACCEPTED", "reason": None},
        {"sequence": 3, "status": "ANOMALY", "reason": "SEQUENCE_GAP"},
    )
    assert not (tmp_path/"observations.jsonl").exists()

def test_open_candle_is_not_observed(tmp_path):
    as_of=datetime(2026,10,7,12,10,tzinfo=timezone.utc)
    frames=[frame(1,as_of-timedelta(minutes=2),100),
            frame(2,as_of-timedelta(minutes=1),101)]
    result=ForwardObservationPathV1(tmp_path/"observations.jsonl").observe(
        frames,as_of=as_of,forward_run_id="OBS-E2E-OPEN")
    assert result.status=="WAITING"
    assert result.reason=="INSUFFICIENT_CLOSED_CANDLES"
