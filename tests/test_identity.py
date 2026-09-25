from core.identity import APP_NAME, OWNER_NAME, validate_identity


def test_canonical_application_identity():
    assert APP_NAME == "HES Trade Agent"
    assert OWNER_NAME == "Seyed Hesameddin Beheshti Shirazi"


def test_identity_integrity():
    validate_identity()
