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


def test_disconnect_reconciles_again_before_reconnect_and_closes_each_socket(monkeypatch):
    stop=Event()
    reconciled=[]
    received=[]
    payload='{"e":"kline","s":"BTCUSDT","E":1000,"k":{"s":"BTCUSDT","i":"1m","x":false}}'

    class DroppedSocket:
        closed=False
        def recv(self):
            raise ConnectionError("simulated_disconnect")
        def close(self):
            self.closed=True

    class RecoverySocket:
        closed=False
        def recv(self):
            stop.set()
            return payload
        def close(self):
            self.closed=True

    dropped=DroppedSocket()
    recovered=RecoverySocket()
    sockets=iter([dropped,recovered])
    fake=SimpleNamespace(
        WebSocketTimeoutException=type("WebSocketTimeoutException",(Exception,),{}),
        create_connection=lambda *args,**kwargs:next(sockets),
    )
    monkeypatch.setitem(sys.modules,"websocket",fake)
    monkeypatch.setattr(stop,"wait",lambda _timeout:False)

    run_spot_kline_stream(
        symbol="BTCUSDT",interval="1m",on_payload=received.append,
        reconcile_history=lambda:reconciled.append(True),stop_event=stop,
        max_reconnects=1,timeout_seconds=1,
    )

    assert reconciled==[True,True]
    assert received==[payload]
    assert dropped.closed and recovered.closed


def test_reconnect_budget_is_bounded_and_failed_socket_is_closed(monkeypatch):
    stop=Event()
    reconciled=[]
    class DroppedSocket:
        closed=False
        def recv(self):
            raise ConnectionError("simulated_disconnect")
        def close(self):
            self.closed=True

    sock=DroppedSocket()
    fake=SimpleNamespace(
        WebSocketTimeoutException=type("WebSocketTimeoutException",(Exception,),{}),
        create_connection=lambda *args,**kwargs:sock,
    )
    monkeypatch.setitem(sys.modules,"websocket",fake)

    with pytest.raises(ConnectionError,match="simulated_disconnect"):
        run_spot_kline_stream(
            symbol="BTCUSDT",interval="1m",on_payload=lambda _:None,
            reconcile_history=lambda:reconciled.append(True),stop_event=stop,
            max_reconnects=0,timeout_seconds=1,
        )

    assert reconciled==[True]
    assert sock.closed
    assert not stop.is_set()
