"""Deterministic session-epoch gate for reconnecting market-data transports.

This module is transport-agnostic and is NOT wired to a production Wallex
WebSocket collector. A caller must stamp every callback with the epoch captured
when its socket was created and gate events before any state mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class EpochEvent(Generic[T]):
    epoch: int
    payload: T


class SessionEpochGate:
    """Thread-safe generation gate; old socket callbacks cannot pass after reconnect."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._epoch = 0
        self._connected = False

    def begin_session(self) -> int:
        """Invalidate all previous sessions and return the new callback epoch."""
        with self._lock:
            self._epoch += 1
            self._connected = True
            return self._epoch

    def end_session(self, epoch: int) -> bool:
        """End only the current session; stale close callbacks are ignored."""
        with self._lock:
            if epoch != self._epoch or not self._connected:
                return False
            self._connected = False
            return True

    def accept(self, event: EpochEvent[T]) -> bool:
        """Return whether an event belongs to the active session."""
        with self._lock:
            return self._connected and event.epoch == self._epoch

    @property
    def current_epoch(self) -> int:
        with self._lock:
            return self._epoch

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected
