from datetime import datetime, timezone
from pathlib import Path

import pytest

from forward.controlled_observation_run_v1 import ControlledObservationRunV1
from forward.forward_observation_writer_v1 import ForwardObservationWriterV1

AS_OF = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)


def rec(ts, seq, price="100"):
    return {
        "source_updated": ts, "symbol": "BTC_USDT", "price": price,
        "amount": "1", "side": "Buy", "sequence": seq,
        "source": "tabdeal_ws_forward_v1",
    }


def test_controlled_run_blocks_before_writer_when_capabilities_unknown(tmp_path: Path):
    output = tmp_path / "obs.jsonl"
    runner = ControlledObservationRunV1(writer=ForwardObservationWriterV1(output))
    with pytest.raises(RuntimeError, match="SEQUENCE_CAPABILITIES_UNVERIFIED"):
        runner.run(
            forward_run_id="FR-001", observed_at=AS_OF,
            records=[rec("2026-10-07T01:01:00+00:00", 1)],
        )
    assert not output.exists()


def test_controlled_run_does_not_process_future_input_before_capability_gate(tmp_path: Path):
    output = tmp_path / "obs.jsonl"
    runner = ControlledObservationRunV1(writer=ForwardObservationWriterV1(output))
    with pytest.raises(RuntimeError, match="SEQUENCE_CAPABILITIES_UNVERIFIED"):
        runner.run(
            forward_run_id="FR-002", observed_at=AS_OF,
            records=[rec("2026-10-07T02:00:01+00:00", 1)],
        )
    assert not output.exists()
