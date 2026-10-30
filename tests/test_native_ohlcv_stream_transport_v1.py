from __future__ import annotations

import json
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream


def test_stream_reconciles_before_connect_and_delivers_payload(monkeypatch):
    stop=Event()
    reconciled=[]
    received=[]
    payload=json.dumps({"e":"kline","s":"BTCUSDT","E":1000,"k":{"s":"BTCUSDT","i":"1m","x":False}})
    class FakeSocket:
        def recv(self):
            stop.set()
            return payload
        def close(self):
            self.closed=True
    sock=FakeSocket()
    fake=SimpleNamespace(
        WebSocketTimeoutException=type("WebSocketTimeoutException",(Exception,),{}),
        create_connection=lambda *args,**kwargs:sock,
    )
    monkeypatch.setitem(sys.modules,"websocket",fake)
    run_spot_kline_stream(symbol="BTCUSDT",interval="1m",on_payload=received.append,
                          reconcile_history=lambda:reconciled.append(True),stop_event=stop)
    assert reconciled==[True]
    assert received==[payload]
    assert sock.closed


def test_invalid_identity_fails_before_import_or_network():
    with pytest.raises(ValueError,match="invalid_stream_identity"):
        run_spot_kline_stream(symbol="btc/usdt",interval="1m",on_payload=lambda _:None,
                              reconcile_history=lambda:None,stop_event=Event())
