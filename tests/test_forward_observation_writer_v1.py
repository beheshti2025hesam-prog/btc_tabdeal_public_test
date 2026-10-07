from __future__ import annotations

import json

import pytest

from forward.forward_observation_writer_v1 import ForwardObservationWriterV1
from forward.runtime_guard_v1 import RuntimeContext


def ctx():
    return RuntimeContext(
        source="tabdeal_forward",
        observed_at="2026-10-07T10:00:00+00:00",
        forward_run_id="RUN-FWD-001",
    )


def obs(event="obs-001"):
    return {
        "event_id": "RUN-FWD-001:" + event,
        "observed_at": "2026-10-07T10:00:00+00:00",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "status": "STRUCTURE_OBSERVED",
        "regime": "UPTREND",
        "source": "tabdeal_forward",
        "outcome": None,
        "closed_at": None,
    }


def test_append_is_hashed_and_durable(tmp_path):
    path = tmp_path / "observations.jsonl"
    digest = ForwardObservationWriterV1(path).append(obs(), context=ctx())
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["digest"] == digest
    assert saved["artifact_type"] == "FORWARD_OBSERVATION"
    assert saved["outcome"] is None


def test_duplicate_event_is_rejected(tmp_path):
    writer = ForwardObservationWriterV1(tmp_path / "observations.jsonl")
    writer.append(obs(), context=ctx())
    with pytest.raises(ValueError, match="duplicate"):
        writer.append(obs(), context=ctx())


def test_historical_and_future_outcome_are_rejected(tmp_path):
    writer = ForwardObservationWriterV1(tmp_path / "observations.jsonl")
    historical = obs("old")
    historical["event_id"] = "RUN-FWD-001:old"
    historical["source"] = "winner"
    with pytest.raises(ValueError, match="historical"):
        writer.append(historical, context=ctx())

    leaked = obs("leak")
    leaked["outcome"] = "WIN"
    with pytest.raises(ValueError, match="outcome"):
        writer.append(leaked, context=ctx())


def test_event_id_is_forward_run_scoped(tmp_path):
    writer = ForwardObservationWriterV1(tmp_path / "observations.jsonl")
    bad = obs()
    bad["event_id"] = "OTHER-RUN:obs-001"
    with pytest.raises(ValueError, match="forward_run_id"):
        writer.append(bad, context=ctx())
