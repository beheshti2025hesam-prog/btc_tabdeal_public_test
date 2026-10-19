"""Opt-in Socket.IO v2-compatible Wallex public market-data transport.

This follows the official API reference's Socket.IO 2.5-compatible contract.
It is intentionally separate from the observed raw-WebSocket /ws transport:
do not silently treat those protocols as interchangeable. No network activity
occurs at import time; callers must explicitly connect and drive a session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import threading
import time
from typing import Any, Callable, Protocol

WALLEX_SOCKETIO_ENDPOINT = "wss://api.wallex.ir/socket.io/?EIO=3&transport=websocket"
_ALLOWED_CHANNELS = frozenset({"trade", "buyDepth", "sellDepth", "marketCap"})


class SocketIOWire(Protocol):
    def recv(self) -> str | bytes: ...
    def send(self, payload: str) -> Any: ...
    def close(self) -> Any: ...


@dataclass(frozen=True)
class WallexSocketIOSession:
    epoch: int
    engine_sid: str
    socketio_sid: str
    socket: SocketIOWire


@dataclass(frozen=True)
class WallexSocketIOEvent:
    epoch: int
    symbol: str
    channel: str
    kind: str
    data: Any
    raw: str
    raw_sha256: str
    received_at_utc: datetime
    received_monotonic_ns: int


class WallexSocketIOTransportV1:
    """Explicit Socket.IO v2 / Engine.IO v3 client with stale-epoch isolation."""

    def __init__(
        self,
        symbol: str,
        *,
        channels: tuple[str, ...] = ("trade",),
        endpoint: str = WALLEX_SOCKETIO_ENDPOINT,
        socket_factory: Callable[[str, float], SocketIOWire] | None = None,
        on_event: Callable[[WallexSocketIOEvent], None] | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(symbol, str) or not symbol or any(c.isspace() for c in symbol) or "@" in symbol:
            raise ValueError("symbol must be non-empty and must not contain whitespace or @")
        if not channels or len(set(channels)) != len(channels) or any(c not in _ALLOWED_CHANNELS for c in channels):
            raise ValueError("channels must be unique members of trade, buyDepth, sellDepth, marketCap")
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
        self._lock = threading.RLock()

    @staticmethod
    def _default_socket_factory(endpoint: str, timeout: float) -> SocketIOWire:
        import websocket
        return websocket.create_connection(
            endpoint, timeout=timeout, enable_multithread=True,
            origin="https://api.wallex.ir",
        )

    @staticmethod
    def _text(raw: str | bytes) -> str:
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        if isinstance(raw, str):
            return raw
        raise ValueError("Socket.IO frame must be text or UTF-8 bytes")

    def _recv_control(self, sock: SocketIOWire, deadline: float) -> str:
        while time.monotonic() < deadline:
            setter = getattr(sock, "settimeout", None)
            if callable(setter):
                setter(max(0.05, min(1.0, deadline - time.monotonic())))
            try:
                message = self._text(sock.recv())
            except Exception as exc:
                if type(exc).__name__ in {"WebSocketTimeoutException", "TimeoutError"}:
                    continue
                raise
            if message == "2":
                sock.send("3")
                continue
            return message
        raise TimeoutError("timed out waiting for Socket.IO handshake")

    def connect(self) -> WallexSocketIOSession:
        with self._lock:
            self._epoch += 1
            epoch = self._epoch
            self._connected = True
        sock: SocketIOWire | None = None
        try:
            sock = self.socket_factory(self.endpoint, self.timeout_seconds)
            deadline = time.monotonic() + self.timeout_seconds
            opening = self._recv_control(sock, deadline)
            if not opening.startswith("0"):
                raise ValueError("expected Engine.IO v3 open packet beginning with 0")
            try:
                engine = json.loads(opening[1:])
            except json.JSONDecodeError as exc:
                raise ValueError("invalid Engine.IO open packet JSON") from exc
            if not isinstance(engine, dict) or not isinstance(engine.get("sid"), str) or not engine["sid"]:
                raise ValueError("Engine.IO open packet must include a non-empty sid")

            sock.send("40")
            ack = self._recv_control(sock, deadline)
            if not ack.startswith("40"):
                raise ValueError("expected Socket.IO namespace connect acknowledgement beginning with 40")
            try:
                ack_obj = json.loads(ack[2:]) if len(ack) > 2 else {}
            except json.JSONDecodeError as exc:
                raise ValueError("invalid Socket.IO connect acknowledgement JSON") from exc
            if not isinstance(ack_obj, dict) or not isinstance(ack_obj.get("sid"), str) or not ack_obj["sid"]:
                raise ValueError("Socket.IO connect acknowledgement must include a non-empty sid")

            session = WallexSocketIOSession(epoch, engine["sid"], ack_obj["sid"], sock)
            with self._lock:
                if not self._connected or epoch != self._epoch:
                    raise RuntimeError("Socket.IO session was superseded during handshake")
                # Serialize subscriptions with epoch changes so a concurrent
                # reconnect cannot supersede this session midway through setup.
                for channel in self.channels:
                    packet = "42" + json.dumps(
                        ["subscribe", {"channel": f"{self.symbol}@{channel}"}],
                        separators=(",", ":"),
                    )
                    sock.send(packet)
                return session
        except Exception:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            with self._lock:
                if epoch == self._epoch:
                    self._connected = False
            raise

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise ValueError(f"{field} must be numeric")
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field} must be numeric") from exc
        if not result.is_finite():
            raise ValueError(f"{field} must be finite")
        return result

    def _validate_market_data(self, kind: str, data: Any) -> None:
        if kind == "trade":
            if not isinstance(data, dict):
                raise ValueError("trade event data must be an object")
            required = {"isBuyOrder", "price", "quantity", "timestamp"}
            if not required.issubset(data):
                raise ValueError("trade event is missing required official fields")
            if not isinstance(data["isBuyOrder"], bool):
                raise ValueError("trade isBuyOrder must be boolean")
            if not isinstance(data["timestamp"], str) or not data["timestamp"]:
                raise ValueError("trade timestamp must be a non-empty string")
            try:
                stamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("trade timestamp must be ISO-8601") from exc
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("trade timestamp must include a timezone")
            if self._decimal(data["price"], "trade price") <= 0:
                raise ValueError("trade price must be positive")
            if self._decimal(data["quantity"], "trade quantity") <= 0:
                raise ValueError("trade quantity must be positive")
        elif kind in {"buyDepth", "sellDepth"}:
            if isinstance(data, dict):
                levels = list(data.values())
            elif isinstance(data, list):
                levels = data
            else:
                raise ValueError("depth event data must be an object or array")
            for level in levels:
                if not isinstance(level, dict) or not {"price", "quantity", "sum"}.issubset(level):
                    raise ValueError("each depth level must contain price, quantity, and sum")
                price = self._decimal(level["price"], "depth price")
                quantity = self._decimal(level["quantity"], "depth quantity")
                total = self._decimal(level["sum"], "depth sum")
                if price <= 0 or quantity < 0 or total < 0:
                    raise ValueError("depth price must be positive and quantity/sum non-negative")
        elif kind == "marketCap":
            if not isinstance(data, dict):
                raise ValueError("marketCap event data must be an object")

    def process_frame(
        self, session: WallexSocketIOSession, raw_frame: str | bytes
    ) -> WallexSocketIOEvent | None:
        raw = self._text(raw_frame)
        with self._lock:
            if not self._connected or session.epoch != self._epoch:
                return None
            if raw == "2":
                session.socket.send("3")
                return None
            if raw == "1" or raw.startswith("41") or raw.startswith("44"):
                self._connected = False
                return None
            if raw in {"3", "6"} or raw.startswith("40"):
                return None
            if not raw.startswith("42"):
                return None
            try:
                packet = json.loads(raw[2:])
            except json.JSONDecodeError as exc:
                raise ValueError("invalid Socket.IO event JSON") from exc
            if not isinstance(packet, list) or len(packet) < 3 or packet[0] != "Broadcaster":
                return None
            channel, data = packet[1], packet[2]
            prefix = f"{self.symbol}@"
            if not isinstance(channel, str) or not channel.startswith(prefix):
                return None
            kind = channel[len(prefix):]
            if kind not in self.channels:
                return None
            self._validate_market_data(kind, data)
            received = self.clock()
            if received.tzinfo is None or received.utcoffset() is None:
                raise ValueError("clock must return a timezone-aware datetime")
            event = WallexSocketIOEvent(
                epoch=session.epoch, symbol=self.symbol, channel=channel, kind=kind,
                data=data, raw=raw, raw_sha256=sha256(raw.encode("utf-8")).hexdigest(),
                received_at_utc=received.astimezone(timezone.utc),
                received_monotonic_ns=self.monotonic_ns(),
            )
            self.on_event(event)
            return event

    def receive_one(self, session: WallexSocketIOSession) -> WallexSocketIOEvent | None:
        raw = self._text(session.socket.recv())
        return self.process_frame(session, raw)

    def close(self, session: WallexSocketIOSession) -> bool:
        try:
            try:
                session.socket.send("41")
            except Exception:
                pass
            session.socket.close()
        finally:
            with self._lock:
                if session.epoch != self._epoch or not self._connected:
                    return False
                self._connected = False
                return True

    @property
    def current_epoch(self) -> int:
        with self._lock:
            return self._epoch

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected
