"""Strict Binance Spot kline event parser for the native OHLCV contract."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .native_ohlcv_v1 import NativeCandle, normalize_native_klines, INTERVAL_MS


class NativeKlineStreamError(ValueError):
    pass


@dataclass(frozen=True)
class NativeKlineEvent:
    symbol: str
    interval: str
    event_time_ms: int
    candle: NativeCandle | None
    payload_sha256: str


def assert_event_matches_batch(event: NativeKlineEvent, batch) -> None:
    """Require exact latest-candle equality before publishing a reconciled batch."""
    if event.candle is None:
        raise NativeKlineStreamError("only_closed_events_can_be_reconciled")
    if (batch.venue, batch.product, batch.symbol, batch.interval) != (
        "binance", "spot", event.symbol, event.interval
    ):
        raise NativeKlineStreamError("rest_batch_scope_mismatch")
    if not batch.candles or batch.candles[-1].open_time_ms != event.candle.open_time_ms:
        raise NativeKlineStreamError("rest_websocket_latest_candle_mismatch")
    fields = ("close_time_ms", "open", "high", "low", "close", "volume",
              "quote_volume", "trade_count", "taker_buy_volume", "taker_buy_quote_volume")
    if any(getattr(batch.candles[-1], field) != getattr(event.candle, field) for field in fields):
        raise NativeKlineStreamError("rest_websocket_candle_field_mismatch")



def parse_kline_event(payload: str | bytes, *, symbol: str, interval: str) -> NativeKlineEvent:
    if interval not in INTERVAL_MS or not symbol.isascii() or symbol != symbol.upper():
        raise NativeKlineStreamError("invalid_stream_identity")
    raw = payload.encode() if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise NativeKlineStreamError("invalid_payload_type")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeKlineStreamError("invalid_json") from exc
    if isinstance(obj, dict) and isinstance(obj.get("data"), dict):
        obj = obj["data"]
    if not isinstance(obj, dict) or obj.get("e") != "kline" or obj.get("s") != symbol:
        raise NativeKlineStreamError("unexpected_event_or_symbol")
    event_time = obj.get("E")
    k = obj.get("k")
    if type(event_time) is not int or not isinstance(k, dict) or k.get("s") != symbol or k.get("i") != interval or type(k.get("x")) is not bool:
        raise NativeKlineStreamError("invalid_kline_identity")
    row = [k.get("t"), k.get("o"), k.get("h"), k.get("l"), k.get("c"), k.get("v"), k.get("T"), k.get("q"), k.get("n"), k.get("V"), k.get("Q"), k.get("B", "0")]
    close_time = k.get("T")
    if type(close_time) is not int:
        raise NativeKlineStreamError("invalid_close_time")
    digest = sha256(raw).hexdigest()
    closed = k["x"]
    as_of = close_time + 1 if closed else close_time
    batch = normalize_native_klines(
        [row], venue="binance", product="spot", symbol=symbol, interval=interval,
        endpoint_kind="websocket_kline", as_of_ms=as_of, fetched_at_ms=max(event_time, as_of),
        response_sha256=digest,
    )
    candle = batch.candles[0] if closed and batch.candles else None
    if closed and candle is None:
        raise NativeKlineStreamError("closed_event_missing_candle")
    return NativeKlineEvent(symbol, interval, event_time, candle, digest)
