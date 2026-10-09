from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1


def rec(seq, price="1"):
    return {"sequence": seq, "price": price, "amount": "1", "symbol": "BTC_USDT"}


def test_clean_monotonic_sequence_is_safe():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11), rec(12)])
    assert r.safe and len(r.accepted) == 3


def test_identical_duplicate_is_idempotent():
    x = rec(10)
    r = CleanEvidenceSequenceGateV1().evaluate([x, x, rec(11)])
    assert r.safe and len(r.accepted) == 2


def test_unverified_numeric_jump_blocks_clean_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12)])
    assert not r.safe and r.reason == "SEQUENCE_GAP_UNVERIFIED"
    assert r.accepted == (rec(10),)


def test_out_of_order_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12), rec(11)])
    assert not r.safe and r.reason in {"SEQUENCE_GAP_UNVERIFIED", "OUT_OF_ORDER_SEQUENCE"}


def test_conflicting_duplicate_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10, "1"), rec(10, "2")])
    assert not r.safe and r.reason == "CONFLICTING_DUPLICATE_SEQUENCE"


def test_invalid_sequence_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec("bad")])
    assert not r.safe and r.reason == "INVALID_SEQUENCE"
