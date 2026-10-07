import json
from datetime import datetime,timezone
from forward.tabdeal_transport_v1 import TabdealReadOnlyTransportV1

ASOF=datetime(2026,10,7,7,0,tzinfo=timezone.utc)
class FakeWS:
 def __init__(self,url,on_open,on_message): self.url=url; self.on_open=on_open; self.on_message=on_message; self.sent=[]
 def send(self,x): self.sent.append(x)
 def run_forever(self,**kwargs):
  self.on_open(self)
  self.on_message(self,json.dumps({"trade":{"symbol":"BTC_USDT","price":"100","amount":"1","side_name":"buy","sequence":1,"updated":"2026-10-07T06:59:00+00:00"}}))
  self.on_message(self,json.dumps({"order":{"x":1}}))
  self.on_message(self,json.dumps({"trade":{"symbol":"ETH_USDT","price":"100","amount":"1","side_name":"buy","sequence":2,"updated":"2026-10-07T06:59:01+00:00"}}))
def test_transport_only_handoffs_records():
 out=[]
 t=TabdealReadOnlyTransportV1(as_of_provider=lambda:ASOF,on_record=out.append,ws_factory=FakeWS)
 t.run_once()
 assert out[0]["source"]=="tabdeal_ws_forward_v1"; assert t.records_emitted==1; assert t.rejected==1
 assert t.frames_seen==3
