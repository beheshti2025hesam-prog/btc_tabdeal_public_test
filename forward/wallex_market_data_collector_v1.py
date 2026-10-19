"""Opt-in Wallex public market-data WebSocket transport.

Wire contract is grounded in pinned read-only captures:
evidence/wallex_ws_reconnect_session_isolation_20261018.json and
evidence/wallex_ws_reconnect_trade_reconciliation_20261018.json.
This is not an official protocol guarantee. No connection is opened at import
time; callers must explicitly create and drive a collector instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from decimal import Decimal, InvalidOperation
import json
import threading
import time
from typing import Any, Callable, Protocol

WALLEX_WS_ENDPOINT = "wss://api.wallex.ir/ws"
_ALLOWED_CHANNELS = frozenset({"trade", "buyDepth", "sellDepth"})


class SocketLike(Protocol):
    def recv(self) -> str | bytes: ...
    def send(self, payload: str) -> Any: ...
    def close(self) -> Any: ...


class StaleWallexSession(RuntimeError):
    """Raised when a connection finishes handshaking after it was superseded."""


@dataclass(frozen=True)
class WallexSession:
    epoch: int
    server_sid: str
    socket: SocketLike


@dataclass(frozen=True)
class WallexMarketEvent:
    epoch: int
    symbol: str
    channel: str
    kind: str
    data: Any
    raw: str
    raw_sha256: str
    received_at_utc: datetime
    received_monotonic_ns: int


class WallexMarketDataCollector:
    """Explicitly driven transport with epoch-isolated event dispatch.

    The first server frame must be the observed session object containing sid.
    The client then sends one JSON subscribe command per requested channel:
    ["subscribe", {"channel": "BTCUSDT@trade"}].
    This class does not infer trade IDs, event ordering, completeness, or volume
    semantics. It does not run a background thread or auto-reconnect itself.
    """

    def __init__(
        self,
        symbol: str,
        *,
        channels: tuple[str, ...] = ("trade",),
        endpoint: str = WALLEX_WS_ENDPOINT,
        socket_factory: Callable[[str, float], SocketLike] | None = None,
        on_event: Callable[[WallexMarketEvent], None] | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(symbol, str) or not symbol or any(c.isspace() for c in symbol) or "@" in symbol:
            raise ValueError("symbol must be a non-empty market symbol without whitespace or @")
        if not channels or len(set(channels)) != len(channels) or any(c not in _ALLOWED_CHANNELS for c in channels):
            raise ValueError("channels must be unique members of trade, buyDepth, sellDepth")
        if not isinstance(endpoint, str) or not endpoint.startswith("wss://"):
            raise ValueError("endpoint must use wss://")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.symbol = symbol
        self.channels = tuple(channels)
        self.endpoint = endpoint
        self.timeout_seconds = float(timeout_seconds)
        self.socket_factory = socket_factory or self._default_socket_factory
        self.on_event = on_event or (lambda event: None)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self._epoch = 0
        self._connected = False
        self._dispatch_lock = threading.RLock()

    @staticmethod
    def _default_socket_factory(endpoint: str, timeout: float) -> SocketLike:
        # Lazy import keeps deterministic parsing/tests usable without the optional dependency.
        import websocket
        return websocket.create_connection(endpoint, timeout=timeout, enable_multithread=True)

    @staticmethod
    def _text(raw: str | bytes) -> str:
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        if isinstance(raw, str):
            return raw
        raise ValueError("WebSocket frame must be text or UTF-8 bytes")

    def connect(self) -> WallexSession:
        """Open one explicit session, validate its first frame, then subscribe."""
        with self._dispatch_lock:
            self._epoch += 1
            epoch = self._epoch
            self._connected = True
        sock: SocketLike | None = None
        try:
            sock = self.socket_factory(self.endpoint, self.timeout_seconds)
            first = json.loads(self._text(sock.recv()))
            if not isinstance(first, dict) or not isinstance(first.get("sid"), str) or not first["sid"]:
                raise ValueError("unexpected Wallex initial session frame: expected object with non-empty sid")
            for channel in self.channels:
                command = ["subscribe", {"channel": f"{self.symbol}@{channel}"}]
                sock.send(json.dumps(command, separators=(",", ":")))
            session = WallexSession(epoch=epoch, server_sid=first["sid"], socket=sock)
            with self._dispatch_lock:
                if not self._connected or epoch != self._epoch:
                    raise StaleWallexSession("session was superseded during handshake")
            return session
        except Exception:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            with self._dispatch_lock:
                if epoch == self._epoch:
                    self._connected = False
            raise

    def process_frame(self, session: WallexSession, raw_frame: str | bytes) -> WallexMarketEvent | None:
        """Parse and dispatch one frame only while its session epoch is current."""
        raw = self._text(raw_frame)
        with self._dispatch_lock:
            if not self._connected or session.epoch != self._epoch:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, list) or len(payload) != 2:
                # Session/heartbeat/control frames are not market events.
                return None
            channel, data = payload
            prefix = f"{self.symbol}@"
            if not isinstance(channel, str) or not channel.startswith(prefix):
                return None
            kind = channel[len(prefix):]
            if kind not in self.channels:
                return None
            if kind == "trade":
                if not isinstance(data, dict):
                    raise ValueError("Wallex trade frame data must be an object")
                required = {"isBuyOrder", "price", "quantity", "timestamp"}
                if not required.issubset(data):
                    raise ValueError("Wallex trade frame is missing required observed fields")
                if not isinstance(data["isBuyOrder"], bool):
                    raise ValueError("isBuyOrder must be boolean")
                for key in ("price", "quantity", "timestamp"):
                    if not isinstance(data[key], str) or not data[key]:
                        raise ValueError(f"{key} must be a non-empty string")
                try:
                    price = Decimal(data["price"])
                    quantity = Decimal(data["quantity"])
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("trade price and quantity must be decimal strings") from exc
                if not price.is_finite() or price <= 0 or not quantity.is_finite() or quantity <= 0:
                    raise ValueError("trade price and quantity must be finite and positive")
                try:
                    stamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("trade timestamp must be ISO-8601") from exc
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("trade timestamp must include a timezone")
            elif not isinstance(data, list):
                raise ValueError("Wallex depth frame data must be an array")
            else:
                for item in data:
                    if not isinstance(item, dict) or not {"price", "quantity", "sum"}.issubset(item):
                        raise ValueError("each Wallex depth item must contain price, quantity, and sum")
                    try:
                        price = Decimal(str(item["price"]))
                        quantity = Decimal(str(item["quantity"]))
                        total = Decimal(str(item["sum"]))
                    except (InvalidOperation, ValueError) as exc:
                        raise ValueError("depth price, quantity, and sum must be numeric") from exc
                    if not all(value.is_finite() for value in (price, quantity, total)):
                        raise ValueError("depth values must be finite")
                    if price <= 0 or quantity < 0 or total < 0:
                        raise ValueError("depth price must be positive and quantity/sum non-negative")
            received = self.clock()
            if received.tzinfo is None or received.utcoffset() is None:
                raise ValueError("clock must return a timezone-aware datetime")
            event = WallexMarketEvent(
                epoch=session.epoch,
                symbol=self.symbol,
                channel=channel,
                kind=kind,
                data=data,
                raw=raw,
                raw_sha256=sha256(raw.encode("utf-8")).hexdigest(),
                received_at_utc=received.astimezone(timezone.utc),
                received_monotonic_ns=self.monotonic_ns(),
            )
            # Keep epoch change and callback dispatch serialized: an old frame
            # cannot begin mutating consumer state after a newer session starts.
            self.on_event(event)
            return event

    def close(self, session: WallexSession) -> bool:
        """Close the socket; a stale session cannot mark a newer one disconnected."""
        try:
            session.socket.close()
        finally:
            with self._dispatch_lock:
                if session.epoch != self._epoch or not self._connected:
                    return False
                self._connected = False
                return True

    @property
    def current_epoch(self) -> int:
        with self._dispatch_lock:
            return self._epoch

    @property
    def connected(self) -> bool:
        with self._dispatch_lock:
            return self._connected
