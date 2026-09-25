from datetime import datetime, timezone
from core.data_engine.candles import Candle, TradeCandleAggregator
from core.data_engine.pressure import BuySellPressureCalculator
from core.data_engine.regime import MarketRegimeClassifier
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.data_engine.vwap import VWAPCalculator
from core.data_engine.normalizer import RawDataNormalizer

def make_trade(seq, sec, price, amount, side="buy"):
    return RawDataNormalizer().normalize_row({"symbol":"BTC_USDT","price":str(price),"amount":str(amount),
        "side":side,"updated":f"2026-09-24T00:00:{sec:02d}Z","sequence":str(seq)})

def make_candle(minute,o,h,l,c,volume=1.0):
    start=datetime(2026,9,24,0,minute,tzinfo=timezone.utc)
    return Candle("BTC_USDT",60,start,start,o,h,l,c,volume,1)

def test_candle_aggregation_is_deterministic():
    result=TradeCandleAggregator(60).aggregate([make_trade(3,30,101,.3),make_trade(1,5,100,.2),make_trade(2,10,103,.1)])
    c=result[0]
    assert (c.open,c.high,c.low,c.close)==(100,103,100,101)
    assert c.volume==.6 and c.trade_count==3

def test_vwap_and_pressure_are_deterministic():
    trades=[make_trade(1,1,100,2,"buy"),make_trade(2,2,110,1,"sell")]
    assert abs(VWAPCalculator().calculate(trades)[0].vwap-310/3)<1e-12
    p=BuySellPressureCalculator().calculate(trades)[0]
    assert p.delta==1 and p.buy_ratio==.6666666666666666

def test_volume_volatility_and_regime():
    candles=[make_candle(0,100,102,99,101,10),make_candle(1,101,104,100,103,10),make_candle(2,103,105,102,104,20)]
    v=VolumeIntelligenceCalculator().calculate(candles)[0]
    assert v.is_volume_spike and abs(v.latest_vs_average-1.5)<1e-12
    vol=VolatilityCalculator().calculate(candles)[0]
    assert vol.return_stddev>0 and vol.average_true_range==(4+3)/2
    regime=MarketRegimeClassifier().classify(candles)[0]
    assert regime.label=="uptrend"
