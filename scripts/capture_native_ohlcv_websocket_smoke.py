"""Bounded read-only Binance Spot WebSocket-to-REST candle reconciliation smoke."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from threading import Event, Timer
import time

from forward.native_ohlcv_v1 import BinanceSpotKlineSource, validate_native_batch
from forward.native_ohlcv_websocket_v1 import parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds",type=int,default=120)
    parser.add_argument("--output",default="evidence/native_ohlcv_websocket_smoke.json")
    args=parser.parse_args()
    if not 30 <= args.timeout_seconds <= 180:
        raise SystemExit("--timeout-seconds must be between 30 and 180")
    source=BinanceSpotKlineSource()
    stop=Event()
    evidence={
        "schema_version":1,"status":"PENDING","venue":"binance","product":"spot",
        "symbol":"BTCUSDT","interval":"1m","execution":"OFF",
        "target":"public_read_only_websocket_vs_rest",
    }

    def reconcile_history():
        batch=source.fetch(symbol="BTCUSDT",interval="1m",limit=240)
        validate_native_batch(batch)
        if not batch.candles:
            raise RuntimeError("rest_history_has_no_closed_candles")
        evidence["rest_reconciliation"]={
            "fetched_at_ms":batch.fetched_at_ms,
            "response_sha256":batch.response_sha256,
            "latest_open_time_ms":batch.candles[-1].open_time_ms,
            "candle_count":len(batch.candles),
            "gap_count":len(batch.gaps),
        }
        return batch

    def on_payload(payload):
        event=parse_kline_event(payload,symbol="BTCUSDT",interval="1m")
        received_ms=int(time.time()*1000)
        delay=received_ms-event.event_time_ms
        if delay < -2000 or delay > 15000:
            raise RuntimeError("websocket_event_stale_or_future")
        if event.candle is None:
            return
        batch=reconcile_history()
        assert_event_matches_batch(event,batch)
        evidence.update({
            "status":"PASS","event_time_ms":event.event_time_ms,
            "event_delay_ms":max(0,delay),"websocket_payload_sha256":event.payload_sha256,
            "matched_candle_open_time_ms":event.candle.open_time_ms,
            "matched_candle_close_time_ms":event.candle.close_time_ms,
            "rest_response_sha256":batch.response_sha256,
            "rest_latest_open_time_ms":batch.candles[-1].open_time_ms,
            "rest_websocket_fields_match":True,
            "completed_at_ms":int(time.time()*1000),
        })
        stop.set()

    timer=Timer(args.timeout_seconds,stop.set)
    timer.daemon=True
    timer.start()
    try:
        run_spot_kline_stream(symbol="BTCUSDT",interval="1m",on_payload=on_payload,
                              reconcile_history=reconcile_history,stop_event=stop,
                              max_reconnects=3,timeout_seconds=10)
    finally:
        timer.cancel()
    if evidence["status"]!="PASS":
        evidence.update(status="BLOCKED",reason="no_reconciled_closed_websocket_candle_before_timeout")
        output=Path(args.output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(evidence,sort_keys=True))
        raise SystemExit("live WebSocket smoke did not produce reconciled evidence")
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(evidence,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
