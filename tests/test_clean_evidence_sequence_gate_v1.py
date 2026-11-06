from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1

def rec(seq,price="1"):
    return {"sequence":seq,"price":price,"amount":"1","symbol":"BTC_USDT"}

def test_empty_input_is_not_clean_forward_evidence():
    result=CleanEvidenceSequenceGateV1().evaluate([])
    assert not result.safe and result.reason=="NO_FORWARD_RECORDS"

def test_unknown_capabilities_block_monotonic_progress():
    records=[rec(10),rec(11),rec(12)]
    result=CleanEvidenceSequenceGateV1().evaluate(records)
    assert not result.safe and result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.accepted==() and result.rejected==tuple(records)

def test_unknown_capabilities_do_not_classify_identical_payload_as_replay():
    item=rec(10)
    result=CleanEvidenceSequenceGateV1().evaluate([item,dict(item),rec(11)])
    assert not result.safe and result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.accepted==()

def test_numeric_jump_is_not_inferred_as_missing_market_event():
    result=CleanEvidenceSequenceGateV1().evaluate([rec(10),rec(12)])
    assert not result.safe and result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"

def test_conflicting_duplicate_is_not_asserted_without_unique_identity_contract():
    result=CleanEvidenceSequenceGateV1().evaluate([rec(10,"1"),rec(10,"2")])
    assert not result.safe and result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
