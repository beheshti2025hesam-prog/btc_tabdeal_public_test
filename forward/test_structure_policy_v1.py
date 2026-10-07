from datetime import datetime, timezone, timedelta
from decimal import Decimal
from forward.candle_normalizer_v1 import Candle15m
from forward.structure_policy_v1 import confirm_swings_v1

BASE=datetime(2026,10,7,0,0,tzinfo=timezone.utc)

def c(i, high, low):
    o=BASE+timedelta(minutes=15*i)
    return Candle15m("BTC_USDT","15m",o,o+timedelta(minutes=15),Decimal(str(high)),Decimal(str(high)),Decimal(str(low)),Decimal(str(high)),Decimal("1"),1,i,i,o,o)

def test_pivot_waits_for_two_right_closed_candles():
    candles=[c(0,101,99),c(1,102,98),c(2,110,97),c(3,103,96),c(4,104,95)]
    before=candles[2].close_time+timedelta(minutes=14)
    assert confirm_swings_v1(candles,observed_at=before)==()
    at=candles[4].close_time
    swings=confirm_swings_v1(candles,observed_at=at)
    assert len(swings)==1
    assert swings[0].kind=="SWING_HIGH"
    assert swings[0].price==Decimal("110")

def test_gap_blocks_confirmation():
    candles=[c(0,101,99),c(1,102,98),c(2,110,97),c(4,104,95),c(5,105,94)]
    assert confirm_swings_v1(candles,observed_at=candles[-1].close_time)==()
