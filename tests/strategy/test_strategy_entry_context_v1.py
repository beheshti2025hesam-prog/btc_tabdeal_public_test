from pathlib import Path
from forward.strategy_entry_context_v1 import build_entry_context, verify_entry_context

NOW=1_800_003_600

def evidence(direction="LONG",regime=None):
    return {"risk":{"state":"RISK_APPROVED"},
            "confirmation":{"state":"CONFIRMED_"+direction},
            "structure":{"status":"OBSERVED","regime":regime or ("UPTREND" if direction=="LONG" else "DOWNTREND")},
            "source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"15m","final_decision":"NO_TRADE"}

def context(direction="LONG",gate=None):
    gate=gate or evidence(direction)
    return build_entry_context(source="gateio_public_spot",symbol="BTC_USDT",candidate_time=NOW,
        policy_version="test-policy-v1",direction=direction,entry=100.0,
        stop=99.0 if direction=="LONG" else 101.0,
        target=103.0 if direction=="LONG" else 97.0,gate_evidence=gate)

def test_valid_context_is_provenance_bound_and_time_limited():
    gate=evidence(); ctx=context(gate=gate)
    assert verify_entry_context(ctx,gate_evidence=gate,now_s=NOW,expected_direction="LONG")== (True,None)
    assert verify_entry_context(ctx,gate_evidence=gate,now_s=NOW+900,expected_direction="LONG")== (True,None)

def test_expired_context_is_rejected():
    gate=evidence(); ctx=context(gate=gate)
    ok,reason=verify_entry_context(ctx,gate_evidence=gate,now_s=NOW+901)
    assert not ok and reason=="ENTRY_CONTEXT_EXPIRED_OR_FUTURE"

def test_context_tampering_is_rejected():
    gate=evidence(); ctx=context(gate=gate); ctx["target_price"]=104.0
    ok,reason=verify_entry_context(ctx,gate_evidence=gate,now_s=NOW)
    assert not ok and reason=="ENTRY_CONTEXT_DIGEST_MISMATCH"

def test_gate_evidence_mismatch_is_rejected():
    gate=evidence(); ctx=context(gate=gate); changed=evidence(); changed["structure"]["regime"]="DOWNTREND"
    ok,reason=verify_entry_context(ctx,gate_evidence=changed,now_s=NOW)
    assert not ok and reason=="ENTRY_CONTEXT_GATE_EVIDENCE_MISMATCH"

def test_risk_or_confirmation_not_approved_cannot_build_context():
    gate=evidence(); gate["risk"]["state"]="RISK_REJECTED"
    try: context(gate=gate)
    except ValueError as exc: assert str(exc)=="ENTRY_CONTEXT_RISK_NOT_APPROVED"
    else: raise AssertionError("risk rejected context must not be built")

def test_wrong_structure_direction_cannot_build_context():
    gate=evidence("LONG","DOWNTREND")
    try: context("LONG",gate)
    except ValueError as exc: assert str(exc)=="ENTRY_CONTEXT_STRUCTURE_DIRECTION_MISMATCH"
    else: raise AssertionError("contradictory structure context must not be built")
