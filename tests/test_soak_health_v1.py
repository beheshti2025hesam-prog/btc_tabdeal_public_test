from forward.soak_health_v1 import ForwardSoakHarnessV1
def test_all_healthy_samples_are_safe():
    h=ForwardSoakHarnessV1()
    for _ in range(1000): h.record(healthy=True)
    s=h.summary()
    assert s.samples==1000 and s.failures==0 and s.safe
def test_single_failure_fails_closed():
    h=ForwardSoakHarnessV1()
    for _ in range(99): h.record(healthy=True)
    h.record(healthy=False)
    s=h.summary()
    assert s.samples==100 and s.failures==1 and not s.safe
def test_empty_run_is_not_safe():
    assert not ForwardSoakHarnessV1().summary().safe
def test_reset_is_explicit():
    h=ForwardSoakHarnessV1(); h.record(healthy=True); h.reset()
    assert h.summary().samples==0 and not h.summary().safe
