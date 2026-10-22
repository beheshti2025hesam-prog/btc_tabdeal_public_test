"""Strict Binance Spot kline parser into the canonical native OHLCV contract.

This module parses payloads only; it never opens a socket or starts a service.
Stream lifecycle remains opt-in and outside this parser.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .native_ohlcv_v1 import INTERVAL_MS, NativeCandle, normalize_native_klines


class NativeKlineStreamError(ValueError):
    """Raised when a WebSocket kline payload violates the source contract."""


@dataclass(frozen=True)
class NativeKlineEvent:
    symbol: str
    interval: str
    event_time_ms: int
    candle: NativeCandle | None
    payload_sha256: str


def parse_kline_event(
    payload: str | bytes, *, symbol: str, interval: str
) -> NativeKlineEvent:
    """Validate one Spot event; admit only closed candles as canonical records."""
    if (
        not isinstance(symbol, str)
        or not symbol.isascii()
        or not symbol
        or symbol != symbol.upper()
        or interval not in INTERVAL_MS
    ):
        raise NativeKlineStreamError("invalid_stream_identity")

    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        raw = payload
    else:
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
    kline = obj.get("k")
    if (
        type(event_time) is not int
        or not isinstance(kline, dict)
        or kline.get("s") != symbol
        or kline.get("i") != interval
        or type(kline.get("x")) is not bool
    ):
        raise NativeKlineStreamError("invalid_kline_identity")

    close_time = kline.get("T")
    if type(close_time) is not int:
        raise NativeKlineStreamError("invalid_close_time")

    row = [
        kline.get("t"), kline.get("o"), kline.get("h"), kline.get("l"),
        kline.get("c"), kline.get("v"), close_time, kline.get("q"),
        kline.get("n"), kline.get("V"), kline.get("Q"), kline.get("B", "0"),
    ]
    digest = sha256(raw).hexdigest()
    as_of_ms = close_time + 1 if kline["x"] else close_time
    try:
        batch = normalize_native_klines(
            [row],
            venue="binance",
            product="spot",
            symbol=symbol,
            interval=interval,
            endpoint_kind="websocket_kline",
            as_of_ms=as_of_ms,
            fetched_at_ms=max(event_time, as_of_ms),
            response_sha256=digest,
        )
    except (TypeError, ValueError) as exc:
        raise NativeKlineStreamError("invalid_kline_candle") from exc

    candle = batch.candles[0] if kline["x"] and batch.candles else None
    if kline["x"] and candle is None:
        raise NativeKlineStreamError("closed_event_missing_candle")
    return NativeKlineEvent(symbol, interval, event_time, candle, digest)
