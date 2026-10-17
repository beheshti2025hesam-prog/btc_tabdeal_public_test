from forward.recovery_idempotent_v1 import ForwardRecoveryControllerV1


def rec(seq, price="100", raw_hash=None):
    record = {
        "source": "tabdeal_ws_forward_v1", "symbol": "BTC_USDT", "price": price,
        "amount": "1", "side": "buy", "source_updated": "2026-10-07T06:30:00+00:00",
        "sequence": seq,
    }
    if raw_hash is not None:
        record["raw_payload_sha256"] = raw_hash
    return record


def test_start_creates_first_clean_segment():
    c = ForwardRecoveryControllerV1(); e = c.start()
    assert e.status == "SEGMENT_STARTED" and e.segment_id == 1
    assert c.observe(rec(100)).status == "ACCEPTED"


def test_reconnect_resets_continuity_without_fabricating_gap():
    c = ForwardRecoveryControllerV1(); c.start()
    assert c.observe(rec(100)).status == "ACCEPTED"
    e = c.reconnect()
    assert e.reason == "TRANSPORT_RECONNECT"
    assert c.observe(rec(1)).status == "ACCEPTED"


def test_restart_never_uses_old_sequence_as_resume_proof():
    c = ForwardRecoveryControllerV1(); c.start()
    assert c.observe(rec(500)).status == "ACCEPTED"
    e = c.restart()
    assert e.reason == "PROCESS_RESTART"
    assert c.observe(rec(1)).status == "ACCEPTED"


def test_identical_raw_payload_replay_is_idempotent_within_segment():
    c = ForwardRecoveryControllerV1(); c.start()
    r = rec(7, raw_hash="a" * 64)
    assert c.observe(r).status == "ACCEPTED"
    assert c.observe(dict(r)).status == "EXACT_REPLAY"


def test_same_opaque_sequence_with_different_payload_is_not_conflict():
    c = ForwardRecoveryControllerV1(); c.start()
    assert c.observe(rec(7, price="100", raw_hash="a" * 64)).status == "ACCEPTED"
    event = c.observe(rec(7, price="101", raw_hash="b" * 64))
    assert event.status == "ACCEPTED"
    assert event.reason == "SEQUENCE_SEMANTICS_UNKNOWN"
