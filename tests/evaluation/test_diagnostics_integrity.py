from core.evaluation.diagnostics import diagnostics_digest, verify_diagnostics


def test_diagnostics_digest_is_stable():
    details = (("quality", "invalid_rows=0"), ("integrity", "gaps=2"))
    assert diagnostics_digest(details) == diagnostics_digest(list(reversed(details)))


def test_diagnostics_tampering_is_detected():
    details = (("quality", "invalid_rows=0"),)
    digest = diagnostics_digest(details)
    tampered = (("quality", "invalid_rows=999"),)
    assert not verify_diagnostics(tampered, digest)


def test_diagnostics_digest_is_separate_from_gate_digest():
    details = (("quality", "invalid_rows=0"),)
    digest = diagnostics_digest(details)
    assert verify_diagnostics(details, digest)
