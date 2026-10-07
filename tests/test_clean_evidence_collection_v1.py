import pytest
from datetime import datetime, timezone, timedelta

from forward.clean_evidence_collection_v1 import ForwardEvidenceRecord


def base():
    return dict(
        forward_run_id="OBS-20261007T080000Z-aabbccddeeff",
        event_id="OBS-20261007T080000Z-aabbccddeeff:candle:1",
        observed_at=datetime.now(timezone.utc),
        symbol="BTC_USDT",
        timeframe="15m",
        status="CANDLE_CLOSED_OBSERVED",
        source="tabdeal_ws_forward_v1",
    )


def test_valid_forward_record():
    ForwardEvidenceRecord(**base())


@pytest.mark.parametrize("field", ["forward_run_id", "event_id"])
def test_identity_required(field):
    data=base(); data[field]=""
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)


def test_naive_time_rejected():
    data=base(); data["observed_at"]=datetime.now()
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)


def test_future_time_rejected():
    data=base(); data["observed_at"]=datetime.now(timezone.utc)+timedelta(seconds=1)
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)


@pytest.mark.parametrize("source", [
    "winner",
    "survivor",
    "legacy",
    "historical",
    "tabdeal_ws_forward_v1:winner",
])
def test_historical_source_rejected(source):
    data=base(); data["source"]=source
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)


def test_wrong_symbol_and_timeframe_rejected():
    data=base(); data["symbol"]="ETH_USDT"
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)
    data=base(); data["timeframe"]="5m"
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)


def test_invalid_status_rejected():
    data=base(); data["status"]="WIN"
    with pytest.raises(ValueError):
        ForwardEvidenceRecord(**data)
