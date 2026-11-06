from datetime import datetime, timezone
import pytest
from forward.forward_tabdeal_ingestion_v1 import ingest_closed_candles, to_trade_observation

AS_OF=datetime(2026,10,7,2,0,tzinfo=timezone.utc)

def rec(ts="2026-10-07T01:01:00+00:00",seq=1,symbol="BTC_USDT"):
    return {"observed_at":"2026-10-07T01:01:01+00:00","source_updated":ts,"symbol":symbol,
            "price":"100.25","amount":"2.0","side":"Buy","sequence":seq,
            "source":"tabdeal_ws_forward_v1"}

def test_trade_observation_conversion_blocks_until_capabilities_are_proven():
    with pytest.raises(ValueError,match="SEQUENCE_CAPABILITIES_UNVERIFIED"):
        to_trade_observation(rec(),as_of=AS_OF)

def test_closed_candle_ingestion_blocks_until_capabilities_are_proven():
    with pytest.raises(ValueError,match="SEQUENCE_CAPABILITIES_UNVERIFIED"):
        ingest_closed_candles([rec()],as_of=AS_OF)

def test_missing_sequence_is_not_replaced_by_another_field():
    item=rec(); item.pop("sequence"); item["id"]=123456
    with pytest.raises(ValueError,match="SEQUENCE_CAPABILITIES_UNVERIFIED"):
        to_trade_observation(item,as_of=AS_OF)
