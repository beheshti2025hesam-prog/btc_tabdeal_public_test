import pytest
from forward.failure_injection_v1 import FailureInjectionMatrixV1
@pytest.mark.parametrize("scenario",[
"DUPLICATE_CONFLICT","SEQUENCE_GAP","OUT_OF_ORDER_SEQUENCE",
"STALE_SOURCE_DATA","SOURCE_RECEIVE_CLOCK_SKEW","TRANSPORT_DISCONNECT",
"PROCESS_RESTART","INVALID_JSON"])
def test_every_injected_failure_fails_closed(scenario):
    r=FailureInjectionMatrixV1().run(scenario)
    assert not r.safe and r.reason==scenario
def test_unknown_failure_is_rejected():
    with pytest.raises(ValueError):
        FailureInjectionMatrixV1().run("UNKNOWN")
