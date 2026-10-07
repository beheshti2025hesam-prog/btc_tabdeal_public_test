from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from forward.candle_normalizer_v1 import Candle15m
from forward.structure_observation_v1 import observe_closed_candles

T=datetime(2026,10,7,2,0,tzinfo=timezone.utc)
def candle(close_time):
    return Candle15m('BTC_USDT','15m',close_time-timedelta(minutes=15),close_time,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),Decimal('1'),1,1,1,close_time-timedelta(minutes=1),close_time-timedelta(minutes=1))

def test_closed_candles_are_observed_but_structure_fails_closed():
    result=observe_closed_candles([candle(T)],observed_at=T)
    assert result.closed_candle_count == 1
    assert result.status == 'UNKNOWN_NO_STRUCTURE_POLICY'
    assert result.snapshot.regime == 'UNKNOWN'

def test_future_candle_rejected():
    with pytest.raises(ValueError,match='after observed_at'):
        observe_closed_candles([candle(T+timedelta(minutes=15))],observed_at=T)

def test_mixed_symbols_rejected():
    other=Candle15m('ETH_USDT','15m',T-timedelta(minutes=15),T,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),Decimal('1'),1,1,1,T,T)
    with pytest.raises(ValueError,match='mixed symbols'):
        observe_closed_candles([candle(T),other],observed_at=T)