from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1


def rec(seq, price="1"):
    return {"sequence": seq, "price": price, "amount": "1", "symbol": "BTC_USDT"}


def verified_gate():
    return CleanEvidenceSequenceGateV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:reviewed-exact-feed-contract",
    )


def test_default_gate_blocks_when_source_contract_is_unverified():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11), rec(12)])
    assert not r.safe
    assert r.reason == "SEQUENCE_CONTRACT_UNVERIFIED"
    assert r.accepted == ()
    assert r.rejected == (rec(10), rec(11), rec(12))


def test_verified_contract_accepts_unique_native_sequences_without_gap_assumptions():
    r = verified_gate().evaluate([rec(10), rec(12), rec(11)])
    assert r.safe and len(r.accepted) == 3
    assert r.reason == "SEQUENCE_CONTRACT_VERIFIED"


def test_identical_repeated_sequence_is_not_idempotently_deduplicated():
    x = rec(10)
    r = verified_gate().evaluate([x, x, rec(11)])
    assert not r.safe
    assert r.reason == "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"
    assert r.accepted == ()


def test_numeric_jump_does_not_itself_prove_loss():
    r = verified_gate().evaluate([rec(10), rec(12)])
    assert r.safe
    assert len(r.accepted) == 2


def test_decreasing_sequence_does_not_itself_prove_out_of_order():
    r = verified_gate().evaluate([rec(12), rec(10), rec(11)])
    assert r.safe
    assert len(r.accepted) == 3


def test_same_sequence_different_payload_blocks_evidence():
    r = verified_gate().evaluate([rec(10, "1"), rec(10, "2")])
    assert not r.safe
    assert r.reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"


def test_native_string_sequence_is_preserved_not_integer_parsed():
    r = verified_gate().evaluate([rec("not-a-number")])
    assert r.safe
    assert r.accepted == (rec("not-a-number"),)


def test_unsupported_sequence_type_blocks_evidence():
    r = verified_gate().evaluate([rec([])])
    assert not r.safe
    assert r.reason == "INVALID_SEQUENCE_TYPE"
