import json
import socket
import threading
from pathlib import Path

import tabdeal_futures_ws_test as collector


def test_emit_liveness_atomically_persists_health_and_notifies(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    heartbeat = tmp_path / "data" / "forward" / "heartbeat.json"
    monkeypatch.setattr(collector, "LOCAL_DURABLE_MODE", True)
    monkeypatch.setattr(collector, "HEARTBEAT_FILE", str(heartbeat))
    monkeypatch.setattr(collector, "last_liveness_emit_monotonic", 0.0)
    monkeypatch.setattr(collector, "last_sequence", 12345)
    monkeypatch.setattr(collector, "trade_count", 7)
    messages = []
    monkeypatch.setattr(collector, "systemd_notify", messages.append)

    assert collector.emit_liveness("READY", force=True, ready=True) is True

    record = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert record["schema"] == "hes_collector_heartbeat_v1"
    assert record["status"] == "RUNNING"
    assert record["event"] == "READY"
    assert record["last_sequence"] == 12345
    assert record["trade_count_this_process"] == 7
    assert messages and "READY=1" in messages[0] and "WATCHDOG=1" in messages[0]
    assert not list(heartbeat.parent.glob("*.tmp"))


def test_systemd_notify_sends_datagram(monkeypatch, tmp_path):
    notify_path = str(tmp_path / "notify.sock")
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(notify_path)
    received = []

    def read_one():
        received.append(receiver.recv(1024).decode("utf-8"))

    thread = threading.Thread(target=read_one, daemon=True)
    thread.start()
    monkeypatch.setenv("NOTIFY_SOCKET", notify_path)

    assert collector.systemd_notify("WATCHDOG=1") is True
    thread.join(timeout=2)
    receiver.close()

    assert received == ["WATCHDOG=1"]


def test_liveness_failure_stops_collector_without_recursive_shutdown(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("block", encoding="utf-8")
    monkeypatch.setattr(collector, "LOCAL_DURABLE_MODE", True)
    monkeypatch.setattr(collector, "HEARTBEAT_FILE", str(blocker / "heartbeat.json"))
    monkeypatch.setattr(collector, "last_liveness_emit_monotonic", 0.0)
    monkeypatch.setattr(collector, "running", True)

    class FakeWebSocket:
        closed = False

        def close(self):
            self.closed = True

    ws = FakeWebSocket()
    monkeypatch.setattr(collector, "current_ws", ws)

    assert collector.emit_liveness("MESSAGE", force=True) is False
    assert collector.running is False
    assert ws.closed is True
