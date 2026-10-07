from datetime import datetime, timezone, timedelta
from forward.regime_engine_v1 import infer_regime_v1, build_regime_snapshot_v1
B=datetime(2026,10,7,0,0,tzinfo=timezone.utc)

def test_uptrend():
    assert infer_regime_v1(("HH","HL","HH","HL"))=="UPTREND"

def test_downtrend():
    assert infer_regime_v1(("LL","LH","LL","LH"))=="DOWNTREND"

def test_unknown_is_fail_closed():
    assert infer_regime_v1(("HH","LH"))=="UNKNOWN"

def test_future_event_rejected():
    from forward.market_structure_v1 import StructureEvent
    from decimal import Decimal
    e=StructureEvent("BOS","BULLISH",B+timedelta(minutes=15),B+timedelta(minutes=15),Decimal("100"),"x")
    try:
        build_regime_snapshot_v1(observed_at=B,labels=("HH","HL"),events=(e,))
        raise AssertionError("future event accepted")
    except ValueError:
        pass
