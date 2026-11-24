from forward.controlled_deployment_gate_v1 import ControlledDeploymentGateV1

def test_preflight_passes_only_when_every_required_condition_is_true():
    gate = ControlledDeploymentGateV1()
    checks = {name: True for name in gate.PREFLIGHT_REQUIRED}
    result = gate.evaluate_preflight(**checks)
    assert result.ready is True
    assert result.phase == "PREFLIGHT"
    assert result.reason == "READY"

def test_preflight_fails_closed_for_each_missing_or_false_condition():
    gate = ControlledDeploymentGateV1()
    for missing in gate.PREFLIGHT_REQUIRED:
        checks = {name: True for name in gate.PREFLIGHT_REQUIRED if name != missing}
        result = gate.evaluate_preflight(**checks)
        assert result.ready is False
        assert result.reason == missing
        checks[missing] = False
        assert gate.evaluate_preflight(**checks).ready is False

def test_postflight_fails_closed_until_services_health_and_stability_pass():
    gate = ControlledDeploymentGateV1()
    checks = {name: True for name in gate.POSTFLIGHT_REQUIRED}
    assert gate.evaluate_postflight(**checks).ready is True
    for missing in gate.POSTFLIGHT_REQUIRED:
        partial = {name: True for name in gate.POSTFLIGHT_REQUIRED if name != missing}
        result = gate.evaluate_postflight(**partial)
        assert result.ready is False
        assert result.reason == missing
