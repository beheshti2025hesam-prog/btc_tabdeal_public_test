from forward.sequence_integrity_v1 import SequenceIntegrityV1


def rec(seq, price="100", **extra):
    return {"sequence": seq, "symbol": "BTC_USDT", "price": price, **extra}


def test_unknown_sequence_semantics_accepts_first_value_without_claiming_order():
    s = SequenceIntegrityV1()
    event = s.observe(rec(10))
    assert event.status == "ACCEPTED"
    assert event.reason == "SEQUENCE_SEMANTICS_UNKNOWN"


def test_opaque_repeated_sequence_with_different_payload_is_not_conflict():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10, "100")).status == "ACCEPTED"
    event = s.observe(rec(10, "101"))
    assert event.status == "ACCEPTED"
    assert event.reason == "SEQUENCE_SEMANTICS_UNKNOWN"


def test_opaque_backward_sequence_is_not_ordering_anomaly():
    s = SequenceIntegrityV1()
    s.observe(rec(12))
    event = s.observe(rec(10))
    assert event.status == "ACCEPTED"
    assert event.reason == "SEQUENCE_SEMANTICS_UNKNOWN"


def test_raw_payload_hash_exact_replay_is_idempotent():
    s = SequenceIntegrityV1()
    raw_hash = "a" * 64
    assert s.observe(rec(10, raw_payload_sha256=raw_hash)).status == "ACCEPTED"
    event = s.observe(rec(10, raw_payload_sha256=raw_hash))
    assert event.status == "EXACT_REPLAY"
    assert event.reason == "RAW_PAYLOAD_SHA256_MATCH"


def test_different_raw_payload_hash_same_sequence_is_not_conflict():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10, raw_payload_sha256="a" * 64)).status == "ACCEPTED"
    event = s.observe(rec(10, "101", raw_payload_sha256="b" * 64))
    assert event.status == "ACCEPTED"
    assert event.reason == "SEQUENCE_SEMANTICS_UNKNOWN"


def test_verified_identity_mode_detects_conflicting_duplicate():
    s = SequenceIntegrityV1(sequence_semantics_verified=True)
    s.observe(rec(10))
    event = s.observe(rec(10, "101"))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_SEQUENCE"
    assert s.last_sequence == 10


def test_verified_ordering_mode_detects_regression():
    s = SequenceIntegrityV1(sequence_semantics_verified=True)
    s.observe(rec(10))
    s.observe(rec(12))
    event = s.observe(rec(11))
    assert event.status == "ANOMALY"
    assert event.reason == "OUT_OF_ORDER_SEQUENCE"
    assert s.last_sequence == 12


def test_exact_normalized_duplicate_only_deduped_in_verified_mode():
    s = SequenceIntegrityV1(sequence_semantics_verified=True)
    r = rec(10)
    s.observe(r)
    assert s.observe(dict(r)).status == "IDEMPOTENT_DUPLICATE"


def test_reconnect_resets_state():
    s = SequenceIntegrityV1()
    s.observe(rec(10, raw_payload_sha256="a" * 64))
    s.reset_for_reconnect()
    assert s.last_sequence is None
    assert s.observe(rec(10, raw_payload_sha256="a" * 64)).status == "ACCEPTED"


def test_invalid_sequence_fails_closed():
    s = SequenceIntegrityV1()
    for value in ("bad", True, False, -1, None):
        try:
            s.observe(rec(value))
        except ValueError as exc:
            assert str(exc) == "invalid sequence"
        else:
            raise AssertionError(f"invalid sequence was accepted: {value!r}")


def test_unique_sequence_state_bound_fails_closed_without_growth():
    s = SequenceIntegrityV1(max_records=2)
    assert s.observe(rec(10)).status == "ACCEPTED"
    assert s.observe(rec(11)).status == "ACCEPTED"
    event = s.observe(rec(12))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SEQUENCE_STATE_BOUND_EXCEEDED"
    assert event.diagnostic == {"max_records": 2}
    assert s._opaque_record_count == 2
