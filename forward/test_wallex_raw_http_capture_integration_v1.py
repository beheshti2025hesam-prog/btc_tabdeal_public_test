from datetime import datetime, timedelta, timezone
import json

import pytest

from forward import wallex_native_candles_v1 as adapter
from forward.wallex_raw_http_evidence_v1 import verify_raw_http_response_v1
from forward.wallex_raw_http_replay_v1 import RawResponseReplayError, replay_raw_http_response_v1
from forward.wallex_candle_observation_v1 import WallexCandleObservationV1

UTC = timezone.utc


class FakeResponse:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.raw


def test_fetch_history_optionally_captures_exact_http_body(tmp_path, monkeypatch):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    start = now - timedelta(minutes=2)
    ts0 = int(start.timestamp())
    payload = {
        "s": "ok",
        "t": [ts0, ts0 + 60],
        "o": ["100", "101"],
        "h": ["102", "103"],
        "l": ["99", "100"],
        "c": ["101", "102"],
        "v": ["0.1", "0.2"],
    }
    raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    monkeypatch.setattr(adapter, "urlopen", lambda request, timeout: FakeResponse(raw))
    evidence_path = tmp_path / "evidence" / "response.json"

    candles = adapter.fetch_history(
        "BTCUSDT", "1", start, now + timedelta(seconds=1),
        raw_evidence_path=evidence_path,
    )

    evidence = verify_raw_http_response_v1(evidence_path)
    assert evidence["raw_body"] == raw
    assert evidence["request_params"]["symbol"] == "BTCUSDT"
    assert evidence["request_params"]["resolution"] == "1"
    assert len(candles) == 2

    as_of = datetime.now(UTC) + timedelta(seconds=5)
    observation = WallexCandleObservationV1(tmp_path / "journal.jsonl").observe(
        candles, as_of=as_of, run_id="raw-replay-test", max_age_seconds=600,
    )
    replay = replay_raw_http_response_v1(
        evidence_path, as_of=as_of, expected_candle_records=observation["candles"],
    )
    assert replay["status"] == "RAW_REPLAY_VERIFIED"
    assert replay["raw_source_replay_verified"] is True
    assert replay["signal_generated"] is False
    assert replay["trade_decision_generated"] is False
    assert replay["execution_enabled"] is False

    tampered = [dict(c) for c in observation["candles"]]
    tampered[0]["close"] = "999"
    with pytest.raises(RawResponseReplayError, match="does not match"):
        replay_raw_http_response_v1(evidence_path, as_of=as_of, expected_candle_records=tampered)
