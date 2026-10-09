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

def test_non_contiguous_sequence_reaches_candle_boundary(tmp_path):
    as_of=datetime(2026,10,7,12,31,tzinfo=timezone.utc)
    frames=[frame(1,as_of-timedelta(minutes=30),100),
            frame(3,as_of-timedelta(minutes=25),101)]
    result=ForwardObservationPathV1(tmp_path/"observations.jsonl").observe(
        frames,as_of=as_of,forward_run_id="OBS-E2E-MONOTONIC")
    assert result.status=="WAITING"
    assert result.reason=="INSUFFICIENT_CLOSED_CANDLES"
    assert result.snapshot_id is None
    assert not (tmp_path/"observations.jsonl").exists()

def test_open_candle_is_not_observed(tmp_path):
    as_of=datetime(2026,10,7,12,10,tzinfo=timezone.utc)
    frames=[frame(1,as_of-timedelta(minutes=2),100),
            frame(2,as_of-timedelta(minutes=1),101)]
    result=ForwardObservationPathV1(tmp_path/"observations.jsonl").observe(
        frames,as_of=as_of,forward_run_id="OBS-E2E-OPEN")
    assert result.status=="WAITING"
    assert result.reason=="INSUFFICIENT_CLOSED_CANDLES"


def test_path_fails_closed_before_processing_over_limit_input(tmp_path):
    as_of = datetime(2026, 10, 7, 12, 31, tzinfo=timezone.utc)
    path = ForwardObservationPathV1(tmp_path / "observations.jsonl", max_records=2)
    frames = [frame(1, as_of-timedelta(minutes=30), 100),
              frame(2, as_of-timedelta(minutes=25), 101),
              frame(3, as_of-timedelta(minutes=15), 102)]
    result = path.observe(frames, as_of=as_of, forward_run_id="OBS-BOUND-001")
    assert result.status == "BLOCKED"
    assert result.reason == "FORWARD_RECORD_BOUND_EXCEEDED"
    assert result.snapshot_id is None
    assert not (tmp_path / "observations.jsonl").exists()


def test_adjacent_pair_structure_context_matches_prefix_semantics():
    from forward.clean_structure_context_v1 import CleanStructureContextV1

    candles = [
        {"symbol":"BTC_USDT", "timeframe":"15m", "status":"CANDLE_CLOSED_OBSERVED",
         "open":str(100+i), "high":str(102+i), "low":str(99+i), "close":str(101+i)}
        for i in range(8)
    ]
    observer = CleanStructureContextV1()
    prefix_contexts = [observer.observe(candles[:i+1]) for i in range(1, len(candles))]
    pair_contexts = [observer.observe(candles[i-1:i+1]) for i in range(1, len(candles))]
    assert [x.bias for x in pair_contexts] == [x.bias for x in prefix_contexts]
    assert [x.higher_close for x in pair_contexts] == [x.higher_close for x in prefix_contexts]
    assert [x.higher_high for x in pair_contexts] == [x.higher_high for x in prefix_contexts]
    assert [x.lower_close for x in pair_contexts] == [x.lower_close for x in prefix_contexts]
    assert [x.lower_low for x in pair_contexts] == [x.lower_low for x in prefix_contexts]
