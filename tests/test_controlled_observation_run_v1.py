from datetime import datetime, timezone
from pathlib import Path

from forward.controlled_observation_run_v1 import ControlledObservationRunV1
from forward.forward_observation_writer_v1 import ForwardObservationWriterV1

AS_OF=datetime(2026,10,7,2,0,tzinfo=timezone.utc)

def rec(ts,seq,price="100"):
    return {"source_updated":ts,"symbol":"BTC_USDT","price":price,"amount":"1","side":"Buy",
            "sequence":seq,"source":"tabdeal_ws_forward_v1"}

def test_controlled_run_writes_closed_candle_and_gap(tmp_path: Path):
    writer=ForwardObservationWriterV1(tmp_path/"obs.jsonl")
    runner=ControlledObservationRunV1(writer=writer)
    digests=runner.run(
        forward_run_id="FR-001",
        observed_at=AS_OF,
        records=[
            rec("2026-10-07T01:01:00+00:00",1),
            rec("2026-10-07T01:31:00+00:00",2),
        ],
    )
    assert len(digests)==2
    lines=(tmp_path/"obs.jsonl").read_text().splitlines()
    assert "CANDLE_CLOSED_OBSERVED" in lines[0]
    assert "NO_TRADE_DATA_GAP" in lines[1]
    assert '"outcome"' not in lines[0]
    assert '"outcome"' not in lines[1]

def test_controlled_run_rejects_future_input(tmp_path: Path):
    runner=ControlledObservationRunV1(writer=ForwardObservationWriterV1(tmp_path/"obs.jsonl"))
    try:
        runner.run(forward_run_id="FR-002",observed_at=AS_OF,
                   records=[rec("2026-10-07T02:00:01+00:00",1)])
        assert False
    except ValueError as exc:
        assert "future" in str(exc)
