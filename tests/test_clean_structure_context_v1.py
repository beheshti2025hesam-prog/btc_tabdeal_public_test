import pytest
from forward.clean_structure_context_v1 import CleanStructureContextV1


def c(o,h,l,cl):
    return {"symbol":"BTC_USDT","timeframe":"15m","status":"CANDLE_CLOSED_OBSERVED","open":str(o),"high":str(h),"low":str(l),"close":str(cl)}


def test_up_context():
    r=CleanStructureContextV1().observe([c(100,102,99,101),c(101,104,100,103)])
    assert r.bias=="UP_CONTEXT" and r.higher_high and r.higher_close


def test_down_context():
    r=CleanStructureContextV1().observe([c(103,104,100,101),c(101,102,98,99)])
    assert r.bias=="DOWN_CONTEXT" and r.lower_low and r.lower_close


def test_mixed_context():
    r=CleanStructureContextV1().observe([c(100,105,99,104),c(104,106,101,102)])
    assert r.bias=="MIXED_CONTEXT"


def test_single_candle_rejected():
    with pytest.raises(ValueError): CleanStructureContextV1().observe([c(1,2,0,1)])


def test_open_candle_rejected():
    x=c(1,2,0,1); x["status"]="OPEN"
    with pytest.raises(ValueError): CleanStructureContextV1().observe([c(1,2,0,1),x])
