"""Binance public OHLCV source for HES (read-only; Spot OR USDⓈ-M Futures).

One explicitly selected market identity is used per source instance. Historical
REST klines and live WebSocket kline events share the same schema. This module
never places orders and never imports credentials. The caller must reconcile
history after reconnects before trusting the stream as gap-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from threading import Event
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time

SPOT_REST = "https://api.binance.com"
USDM_REST = "https://fapi.binance.com"
SPOT_WS = "wss://data-stream.binance.vision"
USDM_WS = "wss://fstream.binance.com/market"
INTERVAL_MS = {"1m": 60_000, "1h": 3_600_000}
REST_PATH = {"spot": "/api/v3/klines", "usdm_futures": "/fapi/v1/klines"}


class BinanceMarketDataError(ValueError):
    """Raised for unsupported identity or invalid upstream market data."""


@dataclass(frozen=True)
class BinanceCandle:
    venue: str
    market: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    is_closed: bool
    source: str


@dataclass(frozen=True)
class BinanceKlineEvent:
    market: str
    symbol: str
    interval: str
    event_time_ms: int
    candle: BinanceCandle
    payload_sha256: str


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise BinanceMarketDataError(f"invalid_{field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BinanceMarketDataError(f"invalid_{field}") from exc
    if not result.is_finite():
        raise BinanceMarketDataError(f"non_finite_{field}")
    return result


def _validate_identity(market: str, symbol: str, interval: str) -> None:
    if market not in REST_PATH:
        raise BinanceMarketDataError("market_must_be_spot_or_usdm_futures")
    if not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum() or not 5 <= len(symbol) <= 30 or symbol != symbol.upper():
        raise BinanceMarketDataError("invalid_symbol")
    if interval not in INTERVAL_MS:
        raise BinanceMarketDataError("supported_intervals_are_1m_and_1h")


def _make_candle(row: Any, *, market: str, symbol: str, interval: str,
                 is_closed: bool, source: str) -> BinanceCandle:
    if not isinstance(row, list) or len(row) < 12:
        raise BinanceMarketDataError("invalid_kline_row")
    step = INTERVAL_MS[interval]
    ot, ct, trades = row[0], row[6], row[8]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (ot, ct, trades)):
        raise BinanceMarketDataError("invalid_kline_integer")
    if ot < 0 or ct != ot + step - 1 or ot % step or trades < 0:
        raise BinanceMarketDataError("invalid_kline_time_or_trade_count")
    op, hi, lo, cl = (_decimal(row[i], n) for i, n in ((1,"open"),(2,"high"),(3,"low"),(4,"close")))
    vol, qvol = _decimal(row[5], "volume"), _decimal(row[7], "quote_volume")
    taker, taker_quote = _decimal(row[9], "taker_buy_volume"), _decimal(row[10], "taker_buy_quote_volume")
    if min(op, hi, lo, cl) <= 0 or min(vol, qvol, taker, taker_quote) < 0:
        raise BinanceMarketDataError("invalid_price_or_volume")
    if hi < max(op, cl, lo) or lo > min(op, cl, hi):
        raise BinanceMarketDataError("invalid_ohlc_range")
    return BinanceCandle("binance", market, symbol, interval, ot, ct, op, hi, lo, cl,
                         vol, qvol, trades, taker, taker_quote, is_closed, source)


def fetch_klines(*, market: str, symbol: str = "BTCUSDT", interval: str = "1m",
                 limit: int = 500, timeout_seconds: float = 8.0,
                 as_of: datetime | None = None) -> tuple[BinanceCandle, ...]:
    """Fetch only fully closed native candles via Binance public REST."""
    _validate_identity(market, symbol, interval)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= (1000 if market == "spot" else 1500):
        raise BinanceMarketDataError("invalid_limit")
    if not 0 < timeout_seconds <= 10:
        raise BinanceMarketDataError("timeout_must_be_between_0_and_10_seconds")
    cutoff = as_of or datetime.now(timezone.utc)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise BinanceMarketDataError("as_of_must_be_timezone_aware")
    base = SPOT_REST if market == "spot" else USDM_REST
    url = base + REST_PATH[market] + "?" + urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
    try:
        with urlopen(request, timeout=float(timeout_seconds)) as response:
            raw = response.read()
        rows = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"binance_rest_failed:{type(exc).__name__}") from exc
    if not isinstance(rows, list):
        raise BinanceMarketDataError("rest_response_not_list")
    now_ms = int(cutoff.timestamp() * 1000)
    result = []
    previous = None
    for row in rows:
        candle = _make_candle(row, market=market, symbol=symbol, interval=interval,
                              is_closed=row[6] < now_ms, source="binance_rest_klines")
        if not candle.is_closed:
            continue
        if previous is not None and candle.open_time_ms <= previous:
            raise BinanceMarketDataError("rest_klines_not_strictly_ordered")
        previous = candle.open_time_ms
        result.append(candle)
    return tuple(result)


def parse_kline_event(payload: str | bytes, *, market: str, symbol: str,
                      interval: str) -> BinanceKlineEvent:
    """Parse raw or combined Spot/USDⓈ-M Futures kline stream envelopes."""
    _validate_identity(market, symbol, interval)
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise BinanceMarketDataError("payload_must_be_text_or_bytes")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BinanceMarketDataError("invalid_websocket_json") from exc
    if isinstance(envelope, dict) and isinstance(envelope.get("data"), dict):
        envelope = envelope["data"]
    if not isinstance(envelope, dict) or envelope.get("e") != "kline":
        raise BinanceMarketDataError("unexpected_websocket_event")
    if envelope.get("s") != symbol or isinstance(envelope.get("E"), bool) or not isinstance(envelope.get("E"), int):
        raise BinanceMarketDataError("websocket_symbol_or_event_time_mismatch")
    k = envelope.get("k")
    if not isinstance(k, dict) or k.get("s") != symbol or k.get("i") != interval or not isinstance(k.get("x"), bool):
        raise BinanceMarketDataError("websocket_kline_identity_or_finality_invalid")
    row = [k.get("t"), k.get("o"), k.get("h"), k.get("l"), k.get("c"), k.get("v"),
           k.get("T"), k.get("q"), k.get("n"), k.get("V"), k.get("Q"), k.get("B", "0")]
    candle = _make_candle(row, market=market, symbol=symbol, interval=interval,
                          is_closed=k["x"], source="binance_websocket_kline")
    return BinanceKlineEvent(market, symbol, interval, envelope["E"], candle, sha256(raw).hexdigest())


def websocket_url(*, market: str, symbol: str, interval: str) -> str:
    _validate_identity(market, symbol, interval)
    stream = f"{symbol.lower()}@kline_{interval}"
    if market == "spot":
        return f"{SPOT_WS}/ws/{stream}"
    return f"{USDM_WS}/ws/{stream}"


def run_kline_stream(*, market: str, symbol: str, interval: str,
                     on_event: Callable[[BinanceKlineEvent], None],
                     reconcile_history: Callable[[int | None], None],
                     stop_event: Event, max_reconnects: int | None = None,
                     timeout_seconds: float = 30.0) -> None:
    """Run supervised read-only stream; reconcile REST history before every connect.

    reconcile_history receives the latest closed candle open-time (or None on
    startup) and must backfill/deduplicate before the stream is trusted. No
    gaps are silently synthesized. Each call owns its socket; caller owns
    durable storage, stale-data policy, process supervision and session isolation.
    """
    _validate_identity(market, symbol, interval)
    if not callable(on_event) or not callable(reconcile_history):
        raise BinanceMarketDataError("callbacks_required")
    if not isinstance(stop_event, Event):
        raise BinanceMarketDataError("threading_event_required")
    if timeout_seconds <= 0 or timeout_seconds > 60:
        raise BinanceMarketDataError("invalid_socket_timeout")
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client dependency is required") from exc

    guard = CandleIngestGuard(market=market, symbol=symbol, interval=interval)
    last_closed_open_ms: int | None = None
    reconnects = 0
    while not stop_event.is_set():
        reconcile_history(last_closed_open_ms)
        if stop_event.is_set():
            break
        socket = None
        try:
            socket = websocket.create_connection(websocket_url(market=market, symbol=symbol, interval=interval),
                                                 timeout=timeout_seconds, enable_multithread=True)
            while not stop_event.is_set():
                try:
                    payload = socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if payload in (None, ""):
                    raise ConnectionError("binance_websocket_closed")
                event = parse_kline_event(payload, market=market, symbol=symbol, interval=interval)
                guard.assert_fresh(event, received_at_ms=int(time.time() * 1000))
                if event.candle.is_closed and not guard.remember_closed(event.candle):
                    continue
                on_event(event)
                if event.candle.is_closed:
                    last_closed_open_ms = event.candle.open_time_ms
        except Exception:
            if stop_event.is_set():
                break
            reconnects += 1
            if max_reconnects is not None and reconnects > max_reconnects:
                raise
            stop_event.wait(min(2 ** min(reconnects - 1, 5), 30))
        finally:
            if socket is not None:
                try:
                    socket.close()
                except Exception:
                    pass


def fetch_canonical_batch(*, market: str, symbol: str = "BTCUSDT", interval: str = "1m",
                          limit: int = 500, as_of: datetime | None = None):
    """Fetch REST candles and pass them through HES's existing canonical bridge."""
    from forward.native_candle_bridge_v1 import normalize_native_candles

    cutoff = as_of or datetime.now(timezone.utc)
    candles = fetch_klines(market=market, symbol=symbol, interval=interval,
                           limit=limit, as_of=cutoff)
    if not candles:
        raise BinanceMarketDataError("no_closed_candles_available")
    return normalize_native_candles(candles, venue="binance", market=market,
                                    as_of=cutoff, source="binance_rest_klines")


def closed_event_to_canonical_batch(event: BinanceKlineEvent, *, as_of: datetime):
    """Convert a final WebSocket event through the existing bridge; open bars return None."""
    from forward.native_candle_bridge_v1 import normalize_native_candles

    if not isinstance(event, BinanceKlineEvent):
        raise BinanceMarketDataError("expected_binance_kline_event")
    if not event.candle.is_closed:
        return None
    return normalize_native_candles([event.candle], venue="binance",
                                    market=event.market, as_of=as_of,
                                    source=event.candle.source)


class StaleMarketDataError(BinanceMarketDataError):
    """Raised when a live event exceeds the configured freshness window."""


class CandleIngestGuard:
    """Session-local closed-candle dedupe and live-event freshness guard.

    This is intentionally in-memory and is not a substitute for durable,
    cross-restart idempotency. Production callers must persist the identity
    and fingerprint before admitting a candle to the analysis/risk engine.
    One instance is bound to exactly one market/symbol/interval profile.
    """

    def __init__(self, *, market: str, symbol: str, interval: str,
                 max_event_delay_ms: int = 15_000,
                 max_future_skew_ms: int = 2_000,
                 max_entries: int = 5_000) -> None:
        _validate_identity(market, symbol, interval)
        for name, value in (("max_event_delay_ms", max_event_delay_ms),
                            ("max_future_skew_ms", max_future_skew_ms),
                            ("max_entries", max_entries)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BinanceMarketDataError(f"invalid_{name}")
        if max_entries == 0:
            raise BinanceMarketDataError("invalid_max_entries")
        self.market = market
        self.symbol = symbol
        self.interval = interval
        self.max_event_delay_ms = max_event_delay_ms
        self.max_future_skew_ms = max_future_skew_ms
        self.max_entries = max_entries
        self._fingerprints: dict[tuple[str, str, str, str, int], tuple[str, ...]] = {}

    def assert_fresh(self, event: BinanceKlineEvent, *, received_at_ms: int) -> int:
        """Return event delay in ms or fail closed for stale/future-dated events."""
        if not isinstance(event, BinanceKlineEvent):
            raise BinanceMarketDataError("expected_binance_kline_event")
        if (event.market, event.symbol, event.interval) != (
            self.market, self.symbol, self.interval
        ):
            raise BinanceMarketDataError("event_profile_mismatch")
        if isinstance(received_at_ms, bool) or not isinstance(received_at_ms, int):
            raise BinanceMarketDataError("invalid_received_at_ms")
        delay = received_at_ms - event.event_time_ms
        if delay < -self.max_future_skew_ms:
            raise StaleMarketDataError("event_timestamp_in_future")
        if delay > self.max_event_delay_ms:
            raise StaleMarketDataError("stale_websocket_event")
        return max(0, delay)

    def remember_closed(self, candle: BinanceCandle) -> bool:
        """Return True for a new closed candle, False for exact semantic replay.

        A repeated identity with changed OHLCV is a conflict, not a silent
        overwrite. Source label is deliberately excluded so matching REST and
        WebSocket copies of the same native candle deduplicate.
        """
        if not isinstance(candle, BinanceCandle):
            raise BinanceMarketDataError("expected_binance_candle")
        if (candle.venue, candle.market, candle.symbol, candle.interval) != (
            "binance", self.market, self.symbol, self.interval
        ):
            raise BinanceMarketDataError("candle_profile_mismatch")
        if not candle.is_closed:
            raise BinanceMarketDataError("only_closed_candles_may_be_deduplicated")
        key = (candle.venue, candle.market, candle.symbol, candle.interval,
               candle.open_time_ms)
        fingerprint = tuple(str(value) for value in (
            candle.close_time_ms, candle.open, candle.high, candle.low, candle.close,
            candle.volume, candle.quote_volume, candle.trade_count,
            candle.taker_buy_base_volume, candle.taker_buy_quote_volume,
        ))
        previous = self._fingerprints.get(key)
        if previous is not None:
            if previous != fingerprint:
                raise BinanceMarketDataError("conflicting_closed_candle_identity")
            return False
        self._fingerprints[key] = fingerprint
        if len(self._fingerprints) > self.max_entries:
            oldest = min(self._fingerprints, key=lambda identity: identity[-1])
            del self._fingerprints[oldest]
        return True
