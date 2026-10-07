"""Minimal read-only Tabdeal WebSocket transport boundary.

The transport owns only socket lifecycle and frame handoff. It never writes
market data, commits Git, starts systemd, evaluates strategy, or executes.
"""
from __future__ import annotations
import json
from typing import Any, Callable
from .tabdeal_readonly_adapter_v1 import parse_trade_frame

WS_URL="wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL="BTC_USDT"

class TabdealReadOnlyTransportV1:
    def __init__(self, *, as_of_provider: Callable[[], Any], on_record: Callable[[dict[str,Any]],None],
                 ws_factory: Callable[...,Any], url: str=WS_URL):
        self.as_of_provider=as_of_provider
        self.on_record=on_record
        self.ws_factory=ws_factory
        self.url=url
        self.frames_seen=0
        self.records_emitted=0
        self.rejected=0

    def _open(self, ws: Any) -> None:
        ws.send(SYMBOL)

    def _message(self, ws: Any, message: str) -> None:
        self.frames_seen += 1
        try:
            payload=json.loads(message)
            trade=payload.get("trade") if isinstance(payload,dict) else None
            if not isinstance(trade,dict):
                return
            frame={
                "type":"trade",
                "symbol":trade.get("symbol",SYMBOL),
                "price":trade.get("price"),
                "amount":trade.get("amount"),
                "side":trade.get("side",trade.get("side_name")),
                "sequence":trade.get("sequence"),
                "timestamp":trade.get("updated"),
            }
            record=parse_trade_frame(frame,as_of=self.as_of_provider())
            self.on_record(record)
            self.records_emitted += 1
        except (ValueError, TypeError, json.JSONDecodeError, KeyError):
            self.rejected += 1

    def run_once(self) -> None:
        ws=self.ws_factory(self.url,on_open=self._open,on_message=self._message)
        ws.run_forever(ping_interval=20,ping_timeout=10)
