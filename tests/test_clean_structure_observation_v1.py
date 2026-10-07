from datetime import datetime, timezone
import pytest
from forward.clean_structure_observation_v1 import CleanStructureObservationV1


def candle():
    return {"symbol":"BTC_USDT","timeframe":"15m","status":"CANDLE_CLOSED_OBSERVED","open":"100","high":"105","low":"98","close":"103"}


def test_closed_candle_is_observed():
    r=CleanStructureObservationV1().observe(candle(), observed_at=datetime.now(timezone.utc))
    assert r.status=="STRUCTURE_OBSERVED" and r.direction=="UP"


def test_open_candle_rejected():
    c=candle(); c["status"]="OPEN"
    with pytest.raises(ValueError): CleanStructureObservationV1().observe(c, observed_at=datetime.now(timezone.utc))


@pytest.mark.parametrize("key,value", [("symbol","ETH_USDT"),("timeframe","5m")])
def test_scope_rejected(key,value):
    c=candle(); c[key]=value
    with pytest.raises(ValueError): CleanStructureObservationV1().observe(c, observed_at=datetime.now(timezone.utc))


def test_invalid_range_rejected():
    c=candle(); c["high"]="90"
    with pytest.raises(ValueError): CleanStructureObservationV1().observe(c, observed_at=datetime.now(timezone.utc))
