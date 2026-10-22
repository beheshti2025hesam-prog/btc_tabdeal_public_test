"""Small read-only Binance Spot kline transport; validation/reconciliation stays upstream."""
from __future__ import annotations
from threading import Event
from typing import Callable
from .native_ohlcv_v1 import INTERVAL_MS


def run_spot_kline_stream(*, symbol: str, interval: str, on_payload: Callable[[str | bytes], None],
                          reconcile_history: Callable[[], None], stop_event: Event,
                          max_reconnects: int | None = None, timeout_seconds: float = 30.0) -> None:
    if interval not in INTERVAL_MS or not symbol.isascii() or symbol != symbol.upper():
        raise ValueError("invalid_stream_identity")
    if not callable(on_payload) or not callable(reconcile_history) or not isinstance(stop_event, Event):
        raise ValueError("invalid_stream_callbacks")
    if not 0 < timeout_seconds <= 60:
        raise ValueError("invalid_timeout")
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client dependency is required") from exc
    url = f"wss://data-stream.binance.vision/ws/{symbol.lower()}@kline_{interval}"
    retries = 0
    while not stop_event.is_set():
        socket = None
        try:
            reconcile_history()
            if stop_event.is_set():
                return
            socket = websocket.create_connection(url, timeout=timeout_seconds, enable_multithread=True)
            while not stop_event.is_set():
                try:
                    payload = socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if payload in (None, ""):
                    raise ConnectionError("stream_closed")
                on_payload(payload)
        except Exception:
            if stop_event.is_set():
                return
            retries += 1
            if max_reconnects is not None and retries > max_reconnects:
                raise
            stop_event.wait(min(2 ** min(retries - 1, 5), 30))
        finally:
            if socket is not None:
                try:
                    socket.close()
                except Exception:
                    pass
