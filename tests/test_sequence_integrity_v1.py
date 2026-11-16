from forward.sequence_integrity_v1 import SequenceIntegrityV1


def rec(seq=None, price="100"):
    return {"sequence": seq, "symbol": "BTC_USDT", "price": price}


def test_first_observation_is_accepted_without_interpreting_sequence():
    s = SequenceIntegrityV1()
    event = s.observe(rec("007"))
    assert event.status == "ACCEPTED"
    assert event.sequence == "007"
    assert s.last_sequence == "007"


def test_native_sequence_representations_are_not_coerced_or_compared():
    s = SequenceIntegrityV1()
    for value in (7, "7", "007"):
        assert s.observe(rec(value)).status == "ACCEPTED"
    assert len(s._records) == 3


def test_same_sequence_different_payload_is_preserved_as_independent_event():
    s = SequenceIntegrityV1()
    first = rec(10, "100")
    second = rec(10, "101")
    assert s.observe(first).status == "ACCEPTED"
    event = s.observe(second)
    assert event.status == "ACCEPTED"
    assert event.reason is None
    assert len(s._records) == 2
    assert s._records == [first, second]


def test_identical_repeated_payload_is_preserved_not_deduplicated():
    s = SequenceIntegrityV1()
    r = rec(10)
    assert s.observe(r).status == "ACCEPTED"
    assert s.observe(dict(r)).status == "ACCEPTED"
    assert len(s._records) == 2


def test_numeric_gaps_and_decreases_do_not_prove_loss_or_order():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10)).status == "ACCEPTED"
    assert s.observe(rec(12)).status == "ACCEPTED"
    assert s.observe(rec(11)).status == "ACCEPTED"
    assert len(s._records) == 3


def test_missing_sequence_metadata_is_allowed():
    s = SequenceIntegrityV1()
    event = s.observe({"symbol": "BTC_USDT", "price": "100"})
    assert event.status == "ACCEPTED"
    assert event.sequence is None
    assert s.last_sequence is None
    assert len(s._records) == 1


def test_reconnect_starts_a_new_local_observation_epoch():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    s.reset_for_reconnect()
    assert s.last_sequence is None
    assert s._records == []
    assert s.observe(rec(10)).status == "ACCEPTED"


def test_invalid_sequence_type_fails_closed_without_coercion():
    s = SequenceIntegrityV1()
    for value in (True, 1.0, [], {}, ""):
        try:
            s.observe(rec(value))
        except ValueError as exc:
            assert str(exc) == "invalid sequence"
        else:
            raise AssertionError(f"invalid sequence accepted: {value!r}")


def test_state_bound_counts_all_observations_not_unique_sequences():
    s = SequenceIntegrityV1(max_records=2)
    assert s.observe(rec(10)).status == "ACCEPTED"
    assert s.observe(rec(10)).status == "ACCEPTED"
    event = s.observe(rec(10))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SEQUENCE_OBSERVATION_BOUND_EXCEEDED"
    assert event.diagnostic == {"max_records": 2}
    assert len(s._records) == 2
