from tests.sequence_registry_fixtures import verified_tabdeal_test_registry
from forward.recovery_idempotent_v1 import ForwardRecoveryControllerV1
from forward.sequence_semantics_v1 import TABDEAL_TRADE_SEQUENCE_KEY

CAPS = verified_tabdeal_test_registry().resolve_tabdeal_trade_sequence()

def rec(seq, price="100"):
    return {"source":"tabdeal_ws_forward_v1","symbol":"BTC_USDT","price":price,"amount":"1","side":"buy","source_updated":"2026-10-07T06:30:00+00:00","sequence":seq}

def test_start_creates_first_clean_segment():
    c=ForwardRecoveryControllerV1(capabilities=CAPS); e=c.start()
    assert e.status=="SEGMENT_STARTED" and e.segment_id==1
    assert c.observe(rec(100)).status=="ACCEPTED"

def test_reconnect_resets_continuity_without_fabricating_gap():
    c=ForwardRecoveryControllerV1(capabilities=CAPS); c.start()
    assert c.observe(rec(100)).status=="ACCEPTED"
    e=c.reconnect()
    assert e.reason=="TRANSPORT_RECONNECT"
    assert c.observe(rec(1)).status=="ACCEPTED"

def test_restart_never_uses_old_sequence_as_resume_proof():
    c=ForwardRecoveryControllerV1(capabilities=CAPS); c.start()
    assert c.observe(rec(500)).status=="ACCEPTED"
    e=c.restart()
    assert e.reason=="PROCESS_RESTART"
    assert c.observe(rec(1)).status=="ACCEPTED"

def test_identical_duplicate_is_idempotent_within_segment():
    c=ForwardRecoveryControllerV1(capabilities=CAPS); c.start(); r=rec(7)
    assert c.observe(r).status=="ACCEPTED"
    assert c.observe(dict(r)).status=="IDEMPOTENT_DUPLICATE"

def test_conflict_still_rejects_after_recovery():
    c=ForwardRecoveryControllerV1(capabilities=CAPS); c.start(); r=rec(7)
    assert c.observe(r).status=="ACCEPTED"
    assert c.observe(rec(7, price="101")).status=="REJECT_STREAM"


def test_recovery_blocks_unknown_sequence_semantics_by_default():
    c=ForwardRecoveryControllerV1(); c.start()
    event=c.observe(rec(1))
    assert event.status=="BLOCKED"
    assert event.reason=="SEQUENCE_SEMANTICS_UNVERIFIED"
