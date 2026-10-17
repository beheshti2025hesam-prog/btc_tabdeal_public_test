from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1


def rec(seq, price="1", **extra):
    return {"sequence": seq, "price": price, "amount": "1", "symbol": "BTC_USDT", **extra}


def test_monotonic_values_are_accepted_without_claiming_sequence_semantics():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11), rec(12)])
    assert r.safe and len(r.accepted) == 3
    assert r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"


def test_same_sequence_different_payload_is_not_assumed_conflict():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10, "1"), rec(10, "2")])
    assert r.safe and len(r.accepted) == 2
    assert r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"


def test_unverified_numeric_jump_does_not_claim_a_gap():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12)])
    assert r.safe and len(r.accepted) == 2
    assert r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"


def test_backwards_value_does_not_claim_out_of_order():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(12), rec(11)])
    assert r.safe and len(r.accepted) == 3
    assert r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"


def test_exact_raw_payload_replay_is_suppressed():
    r = CleanEvidenceSequenceGateV1().evaluate([
        rec(10, raw_payload_sha256="a" * 64),
        rec(10, raw_payload_sha256="a" * 64),
    ])
    assert r.safe and len(r.accepted) == 1


def test_invalid_sequence_blocks_evidence():
    r = CleanEvidenceSequenceGateV1().evaluate([rec("bad")])
    assert not r.safe and r.reason == "INVALID_SEQUENCE"
