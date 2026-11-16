from datetime import datetime, timezone

from forward.forward_reliability_guard_v1 import ReliabilityGuardV1

G = ReliabilityGuardV1()


def test_timestamp_validation():
    now = datetime.now(timezone.utc)
    G.validate_timestamp(now, as_of=now)


def test_future_timestamp_rejected():
    now = datetime.now(timezone.utc)
    future = now.replace(year=now.year + 1)
    try:
        G.validate_timestamp(future, as_of=now)
    except ValueError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("future timestamp must be rejected")


def test_sequence_is_optional_opaque_metadata_without_coercion():
    assert G.validate_sequence("12") == "12"
    assert G.validate_sequence(-1) == -1
    assert G.validate_sequence(None) is None
    assert G.validate_sequence({"provider_value": 12}) == {"provider_value": 12}


def test_sequence_equality_does_not_establish_duplicate_identity():
    previous = {"sequence": 1, "price": "100"}
    current = {"sequence": 1, "price": "101"}
    assert G.validate_duplicate(previous, current) is None
    assert G.validate_duplicate(previous, previous) is None


def test_reason_required():
    assert G.require_reason("  NO_TRADE  ") == "NO_TRADE"
