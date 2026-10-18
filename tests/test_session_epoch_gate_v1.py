import threading

from forward.session_epoch_gate_v1 import EpochEvent, SessionEpochGate


def test_new_session_invalidates_old_epoch():
    gate = SessionEpochGate()
    old = gate.begin_session()
    new = gate.begin_session()
    assert new == old + 1
    assert not gate.accept(EpochEvent(old, {"kind": "trade"}))
    assert gate.accept(EpochEvent(new, {"kind": "trade"}))


def test_disconnect_rejects_current_epoch_events():
    gate = SessionEpochGate()
    epoch = gate.begin_session()
    assert gate.end_session(epoch)
    assert not gate.accept(EpochEvent(epoch, "late-frame"))


def test_stale_close_callback_cannot_disconnect_new_session():
    gate = SessionEpochGate()
    old = gate.begin_session()
    new = gate.begin_session()
    assert not gate.end_session(old)
    assert gate.connected
    assert gate.accept(EpochEvent(new, "current"))


def test_duplicate_current_epoch_events_are_identified_as_current():
    gate = SessionEpochGate()
    epoch = gate.begin_session()
    event = EpochEvent(epoch, {"id": 7})
    assert gate.accept(event)
    assert gate.accept(event)
    # Deduplication is a separate concern; this gate only isolates sessions.


def test_out_of_order_events_from_same_session_are_not_session_stale():
    gate = SessionEpochGate()
    epoch = gate.begin_session()
    assert gate.accept(EpochEvent(epoch, {"sequence": 12}))
    assert gate.accept(EpochEvent(epoch, {"sequence": 11}))
    # Sequence ordering must be enforced by the protocol-specific consumer.


def test_reconnect_loop_only_accepts_latest_epoch():
    gate = SessionEpochGate()
    epochs = [gate.begin_session() for _ in range(25)]
    assert all(not gate.accept(EpochEvent(e, "old")) for e in epochs[:-1])
    assert gate.accept(EpochEvent(epochs[-1], "latest"))


def test_end_session_is_idempotent():
    gate = SessionEpochGate()
    epoch = gate.begin_session()
    assert gate.end_session(epoch)
    assert not gate.end_session(epoch)


def test_concurrent_begin_session_returns_unique_epochs():
    gate = SessionEpochGate()
    values = []
    lock = threading.Lock()

    def worker():
        value = gate.begin_session()
        with lock:
            values.append(value)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(values)) == 40
    assert gate.current_epoch == max(values)
