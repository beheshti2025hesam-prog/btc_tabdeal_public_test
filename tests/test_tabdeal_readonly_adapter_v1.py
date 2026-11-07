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
 parsed=parse_trade_frame(x,as_of=ASOF)
 assert "sequence" not in parsed
def test_rejects_bad_values():
 for key,val in [("price","0"),("amount","-1"),("side","hold")]:
  x=base(); x[key]=val
  with pytest.raises(ValueError): parse_trade_frame(x,as_of=ASOF)


@pytest.mark.parametrize("alias", ["seq", "id"])
def test_does_not_promote_generic_aliases_to_trade_sequence(alias):
    x = base()
    x.pop("sequence")
    x[alias] = 7
    parsed = parse_trade_frame(x, as_of=ASOF)
    assert "sequence" not in parsed


@pytest.mark.parametrize("value", [False, True, 7.0, "7", None])
def test_sequence_is_preserved_as_opaque_metadata_without_coercion(value):
    x = base()
    x["sequence"] = value
    parsed = parse_trade_frame(x, as_of=ASOF)
    assert "sequence" in parsed
    assert parsed["sequence"] == value
    assert type(parsed["sequence"]) is type(value)


def test_missing_optional_sequence_metadata_does_not_reject_core_trade():
    x = base()
    del x["sequence"]
    parsed = parse_trade_frame(x, as_of=ASOF)
    assert parsed["symbol"] == "BTC_USDT"
    assert parsed["price"] == "100"
    assert parsed["amount"] == "0.1"
    assert "sequence" not in parsed
