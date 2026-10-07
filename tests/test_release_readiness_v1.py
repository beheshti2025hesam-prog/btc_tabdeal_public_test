import pytest
from forward.release_readiness_v1 import ReleaseReadinessGateV1
REQUIRED=ReleaseReadinessGateV1.REQUIRED

def base():
    return {k: True for k in REQUIRED}

@pytest.mark.parametrize("name", REQUIRED)
def test_any_failed_release_check_blocks_promotion(name):
    checks=base(); checks[name]=False
    r=ReleaseReadinessGateV1().evaluate(**checks)
    assert r.ready is False and r.reason==name

def test_missing_check_blocks_promotion():
    checks=base(); checks.pop("git_integrity_pass")
    r=ReleaseReadinessGateV1().evaluate(**checks)
    assert r.ready is False and r.reason=="git_integrity_pass"

def test_all_checks_pass_is_ready():
    r=ReleaseReadinessGateV1().evaluate(**base())
    assert r.ready is True and r.reason=="READY"
