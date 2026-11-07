from tests.sequence_registry_fixtures import verified_tabdeal_test_registry
from forward.sequence_integrity_v1 import SequenceIntegrityV1
from forward.sequence_semantics_v1 import TABDEAL_TRADE_SEQUENCE_KEY

CAPS = verified_tabdeal_test_registry().resolve_tabdeal_trade_sequence()


def rec(seq, price="100"):
    return {"sequence": seq, "symbol": "BTC_USDT", "price": price, "sequence_contract_key": TABDEAL_TRADE_SEQUENCE_KEY}


def test_first_sequence_accepted():
    s = SequenceIntegrityV1(capabilities=CAPS)
    assert s.observe(rec(10)).status == "ACCEPTED"


def test_identical_duplicate_is_idempotent():
    s = SequenceIntegrityV1(capabilities=CAPS)
    r = rec(10)
    s.observe(r)
    event = s.observe(dict(r))
    assert event.status == "IDEMPOTENT_DUPLICATE"
    assert s.last_sequence == 10


def test_conflicting_duplicate_rejects_stream():
    s = SequenceIntegrityV1(capabilities=CAPS)
    s.observe(rec(10))
    event = s.observe(rec(10, price="101"))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_IDENTITY"
    assert s.last_sequence == 10


def test_non_contiguous_monotonic_sequence_is_accepted():
    s = SequenceIntegrityV1(capabilities=CAPS)
    s.observe(rec(10))
    event = s.observe(rec(12))
    assert event.status == "ACCEPTED"
    assert event.reason is None
    assert s.last_sequence == 12


def test_out_of_order_is_anomaly_and_does_not_reorder():
    s = SequenceIntegrityV1(capabilities=CAPS)
    s.observe(rec(10))
    s.observe(rec(12))
    event = s.observe(rec(11))
    assert event.status == "ANOMALY"
    assert event.reason == "OUT_OF_ORDER_SEQUENCE"
    assert s.last_sequence == 12


def test_reconnect_resets_continuity_without_fabrication():
    s = SequenceIntegrityV1(capabilities=CAPS)
    s.observe(rec(10))
    s.reset_for_reconnect()
    assert s.last_sequence is None
    assert s.observe(rec(100)).status == "ACCEPTED"


def test_invalid_sequence_fails_closed():
    event = SequenceIntegrityV1(capabilities=CAPS).observe(rec("bad"))
    assert event.status == "BLOCKED"
    assert event.reason == "SEQUENCE_VALUE_MUST_BE_NONNEGATIVE_INTEGER"


def test_unique_sequence_state_bound_fails_closed_without_growth():
    s = SequenceIntegrityV1(capabilities=CAPS, max_records=2)
    assert s.observe(rec(10)).status == "ACCEPTED"
    assert s.observe(rec(11)).status == "ACCEPTED"
    event = s.observe(rec(12))
    assert event.status == "REJECT_STREAM"
    assert event.reason == "SEQUENCE_STATE_BOUND_EXCEEDED"
    assert event.diagnostic == {"max_records": 2}
    assert s.records_count == 2
