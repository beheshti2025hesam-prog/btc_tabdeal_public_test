from forward.sequence_integrity_v1 import SequenceIntegrityV1


def rec(seq, price="100"):
    return {"sequence": seq, "symbol": "BTC_USDT", "price": price}


def test_first_sequence_accepted():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10)).status == "ACCEPTED"


def test_identical_duplicate_is_idempotent():
    s = SequenceIntegrityV1()
    r = rec(10)
    s.observe(r)
    event = s.observe(dict(r))
    assert event.status == "IDEMPOTENT_DUPLICATE"
    assert s.last_sequence == 10


def test_conflicting_duplicate_rejects_stream():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    event = s.observe(rec(10, price="101"))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_SEQUENCE"
    assert s.last_sequence == 10


def test_gap_is_anomaly_without_repair():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    event = s.observe(rec(12))
    assert event.status == "ANOMALY"
    assert event.reason == "SEQUENCE_GAP"
    assert s.last_sequence == 12


def test_out_of_order_is_anomaly_and_does_not_reorder():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    s.observe(rec(12))
    event = s.observe(rec(11))
    assert event.status == "ANOMALY"
    assert event.reason == "OUT_OF_ORDER_SEQUENCE"
    assert s.last_sequence == 12


def test_reconnect_resets_continuity_without_fabrication():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    s.reset_for_reconnect()
    assert s.last_sequence is None
    assert s.observe(rec(100)).status == "ACCEPTED"


def test_invalid_sequence_fails_closed():
    s = SequenceIntegrityV1()
    try:
        s.observe(rec("bad"))
    except ValueError as exc:
        assert str(exc) == "invalid sequence"
    else:
        raise AssertionError("invalid sequence was accepted")
