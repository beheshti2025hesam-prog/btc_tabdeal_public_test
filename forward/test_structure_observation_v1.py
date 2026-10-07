from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from forward.candle_normalizer_v1 import Candle15m
from forward.structure_observation_v1 import observe_closed_candles

T=datetime(2026,10,7,2,0,tzinfo=timezone.utc)

def candle(open_time, close, high, low, seq):
    return Candle15m('BTC_USDT','15m',open_time,close,Decimal('100'),Decimal(str(high)),Decimal(str(low)),Decimal('100'),Decimal('1'),1,seq,seq,close-timedelta(minutes=1),close-timedelta(minutes=1))

def test_no_confirmed_swing_fails_closed():
    result=observe_closed_candles([candle(T-timedelta(minutes=15),T,101,99,1)],observed_at=T)
    assert result.status == 'UNKNOWN_NO_CONFIRMED_SWINGS'
    assert result.snapshot.regime == 'UNKNOWN'

def test_confirmed_pivot_is_exposed_only_after_two_right_closed_candles():
    start=T-timedelta(minutes=75)
    vals=[(start+i*timedelta(minutes=15),101,99) for i in range(6)]
    vals[2]=(vals[2][0],110,90)
    candles=[candle(o,o+timedelta(minutes=15),h,l,i+1) for i,(o,h,l) in enumerate(vals)]
    before=vals[4][0]+timedelta(minutes=15)-timedelta(seconds=1)
    result=observe_closed_candles(candles,observed_at=before)
    assert result.snapshot.last_high is None
    result=observe_closed_candles(candles,observed_at=vals[4][0]+timedelta(minutes=15))
    assert result.snapshot.last_high is not None
    assert result.snapshot.last_high.price == Decimal('110')

def test_future_candle_rejected():
    with pytest.raises(ValueError,match='after observed_at'):
        observe_closed_candles([candle(T,T+timedelta(minutes=15),101,99,1)],observed_at=T)

def test_mixed_symbols_rejected():
    other=Candle15m('ETH_USDT','15m',T-timedelta(minutes=15),T,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),Decimal('1'),1,1,1,T,T)
    with pytest.raises(ValueError,match='mixed symbols'):
        observe_closed_candles([candle(T-timedelta(minutes=15),T,101,99,1),other],observed_at=T)
