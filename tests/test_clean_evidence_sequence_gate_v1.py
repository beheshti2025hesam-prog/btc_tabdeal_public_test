from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1
from forward.sequence_semantics_v1 import TABDEAL_TRADE_SEQUENCE_KEY
from tests.sequence_registry_fixtures import verified_tabdeal_test_registry

CAPS = verified_tabdeal_test_registry().resolve_tabdeal_trade_sequence()


def rec(seq, price="1"):
    return {"sequence": seq, "price": price, "amount": "1", "symbol": "BTC_USDT", "sequence_contract_key": TABDEAL_TRADE_SEQUENCE_KEY}


def test_clean_monotonic_sequence_is_safe():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11), rec(12)], capabilities=CAPS)
    assert r.safe and len(r.accepted) == 3


def test_identical_duplicate_is_idempotent():
    x = rec(10)
    r = CleanEvidenceSequenceGateV1().evaluate([x, x, rec(11)], capabilities=CAPS)
    assert r.safe and len(r.accepted) == 2


def test_numeric_jump_is_not_a_gap_without_contiguity_capability():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12)], capabilities=CAPS)
    assert r.safe and len(r.accepted) == 2


def test_out_of_order_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12), rec(11)], capabilities=CAPS)
    assert not r.safe and r.reason == "OUT_OF_ORDER_SEQUENCE"


def test_conflicting_duplicate_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10, "1"), rec(10, "2")], capabilities=CAPS)
    assert not r.safe and r.reason == "CONFLICTING_DUPLICATE_IDENTITY"


def test_invalid_sequence_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec("bad")], capabilities=CAPS)
    assert not r.safe and r.reason == "SEQUENCE_VALUE_MUST_BE_NONNEGATIVE_INTEGER"


def test_unknown_semantics_block_by_default():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11)])
    assert not r.safe and r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"
