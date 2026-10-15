from datetime import datetime,timezone
import pytest
from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame
ASOF=datetime(2026,10,7,7,0,tzinfo=timezone.utc)
def base(): return {"type":"trade","symbol":"BTC_USDT","price":"100","amount":"0.1","side":"buy","sequence":7,"timestamp":1791356400000}
def test_normalizes_frame():
 r=parse_trade_frame(base(),as_of=ASOF); assert r["source"]=="tabdeal_ws_forward_v1"; assert r["sequence"]==7
def test_rejects_future():
 x=base(); x["timestamp"]=1791356401000
 with pytest.raises(ValueError,match="future"): parse_trade_frame(x,as_of=ASOF)
def test_rejects_scope_and_incomplete():
 x=base(); x["symbol"]="ETH_USDT"
 with pytest.raises(ValueError): parse_trade_frame(x,as_of=ASOF)
 x=base(); del x["sequence"]
 with pytest.raises(ValueError): parse_trade_frame(x,as_of=ASOF)
def test_rejects_bad_values():
 for key,val in [("price","0"),("amount","-1"),("side","hold"),("sequence",-1)]:
  x=base(); x[key]=val
  with pytest.raises(ValueError): parse_trade_frame(x,as_of=ASOF)

def test_transport_payload_digest_survives_normalization_and_exact_replay_is_detected():
    from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1

    x = base()
    x["timestamp"] = 1791354600000  # 06:30 UTC; the 06:30 candle is closed by ASOF.
    x["raw_payload_sha256"] = "a" * 64
    record = parse_trade_frame(x, as_of=ASOF)
    assert record["raw_payload_sha256"] == "a" * 64

    result = SequenceAwareCandleIngestionV1().ingest(
        [record, dict(record)], as_of=ASOF
    )
    assert [event.status for event in result.events] == ["ACCEPTED", "EXACT_REPLAY"]
    assert len(result.candles) == 1
    assert result.candles[0].trade_count == 1
