from core.evaluation.diagnostics import diagnostics_digest, verify_diagnostics


def test_diagnostics_digest_is_order_independent():
    left = (("quality", "valid"), ("coverage", "complete"))
    right = (("coverage", "complete"), ("quality", "valid"))
    assert diagnostics_digest(left) == diagnostics_digest(right)


def test_diagnostics_tampering_is_detected():
    details = (("quality", "valid"),)
    digest = diagnostics_digest(details)
    assert verify_diagnostics(details, digest)
    assert not verify_diagnostics((("quality", "tampered"),), digest)


def test_empty_diagnostics_have_a_stable_digest():
    digest = diagnostics_digest(())
    assert verify_diagnostics((), digest)
