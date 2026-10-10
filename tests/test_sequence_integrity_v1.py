from forward.sequence_integrity_v1 import SequenceIntegrityV1


def rec(seq, price="100"):
    return {"sequence": seq, "symbol": "BTC_USDT", "price": price}


def test_first_sequence_is_accepted_without_interpreting_value():
    s = SequenceIntegrityV1()
    event = s.observe(rec("007"))
    assert event.status == "ACCEPTED"
    assert event.sequence == "007"
    assert s.last_sequence == "007"


def test_native_sequence_representations_are_not_coerced():
    s = SequenceIntegrityV1()
    assert s.observe(rec(7)).status == "ACCEPTED"
    assert s.observe(rec("7")).status == "ACCEPTED"
    assert s.observe(rec("007")).status == "ACCEPTED"
    assert len(s._records) == 3


def test_same_sequence_different_payload_is_reuse_not_duplicate():
    s = SequenceIntegrityV1()
    first = rec(10, "100")
    s.observe(first)
    event = s.observe(rec(10, "101"))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"
    assert event.diagnostic["same_payload"] is False
    assert event.diagnostic["differing_fields"] == ["price"]
    assert len(s._records) == 2
    assert s._records[0] == first
    assert s._records[1]["price"] == "101"


def test_identical_repeated_payload_is_not_silently_deduplicated():
    s = SequenceIntegrityV1()
    r = rec(10)
    s.observe(r)
    event = s.observe(dict(r))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"
    assert event.diagnostic["same_payload"] is True
    assert len(s._records) == 2


def test_numeric_gaps_do_not_prove_loss():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10)).status == "ACCEPTED"
    event = s.observe(rec(12))
    assert event.status == "ACCEPTED"
    assert event.reason is None


def test_decreasing_sequence_is_not_assumed_to_be_out_of_order():
    s = SequenceIntegrityV1()
    assert s.observe(rec(12)).status == "ACCEPTED"
    event = s.observe(rec(11))
    assert event.status == "ACCEPTED"
    assert event.reason is None
    assert s.last_sequence == 11


def test_reconnect_starts_a_new_sequence_observation_epoch():
    s = SequenceIntegrityV1()
    s.observe(rec(10))
    s.reset_for_reconnect()
    assert s.last_sequence is None
    assert s._records == []
    assert s.observe(rec(10)).status == "ACCEPTED"


def test_invalid_sequence_type_fails_closed_without_coercion():
    s = SequenceIntegrityV1()
    for value in (None, True, 1.0, [], {}, ""):
        try:
            s.observe(rec(value))
        except ValueError as exc:
            assert str(exc) == "invalid sequence"
        else:
            raise AssertionError(f"invalid sequence accepted: {value!r}")


def test_state_bound_counts_all_observations_not_unique_sequences():
    s = SequenceIntegrityV1(max_records=2)
    assert s.observe(rec(10)).status == "ACCEPTED"
    assert s.observe(rec(11)).status == "ACCEPTED"
    event = s.observe(rec(12))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SEQUENCE_STATE_BOUND_EXCEEDED"
    assert event.diagnostic == {"max_records": 2}
    assert len(s._records) == 2


def test_repeated_sequence_after_other_values_is_still_detected():
    s = SequenceIntegrityV1()
    assert s.observe(rec(10, "100")).status == "ACCEPTED"
    assert s.observe(rec(11, "110")).status == "ACCEPTED"
    event = s.observe(rec(10, "101"))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"
    assert len(s._records) == 3
