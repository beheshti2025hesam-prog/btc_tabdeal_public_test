from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from forward.source_health_evidence_v1 import SourceHealthEvidenceV1, evaluate_source_health

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def evidence(**changes):
    value = SourceHealthEvidenceV1(
        schema="hes_source_health_evidence_v1",
        venue="tabdeal",
        product="futures_margin",
        endpoint="wss://api1.tabdeal.org/special_margin/broadcast/",
        topic="BTC_USDT",
        expected_symbol="BTC_USDT",
        observed_symbol="BTC_USDT",
        session_id="session-1",
        connection_id="connection-1",
        connection_generation=1,
        source_event_time=NOW - timedelta(seconds=1),
        received_at=NOW - timedelta(seconds=1),
        schema_valid=True,
        validation_outcome="PASS",
        reason_code="VALID_TRADE_MESSAGE",
    )
    return replace(value, **changes)


def evaluate(item, **overrides):
    args = dict(
        now=NOW, expected_venue="tabdeal", expected_product="futures_margin",
        expected_endpoint="wss://api1.tabdeal.org/special_margin/broadcast/",
        expected_topic="BTC_USDT", expected_symbol="BTC_USDT",
        expected_session_id="session-1", max_age_seconds=5,
    )
    args.update(overrides)
    return evaluate_source_health(item, **args)


def test_valid_fresh_scoped_evidence_is_healthy():
    assert evaluate(evidence()).healthy


@pytest.mark.parametrize("item", [None, "not-evidence"])
def test_missing_or_wrong_evidence_fails_closed(item):
    result = evaluate(item)
    assert not result.healthy


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"),
    ("venue", "other"),
    ("product", "spot"),
    ("endpoint", "wss://wrong.example/"),
    ("topic", "ETH_USDT"),
    ("expected_symbol", "ETH_USDT"),
    ("observed_symbol", "ETH_USDT"),
    ("session_id", "old-session"),
    ("connection_generation", 0),
    ("schema_valid", False),
    ("validation_outcome", "FAIL"),
    ("reason_code", ""),
])
def test_scope_and_claim_tampering_fail_closed(field, value):
    assert not evaluate(evidence(**{field: value})).healthy


def test_stale_receive_time_fails_closed():
    item = evidence(received_at=NOW - timedelta(seconds=6),
                    source_event_time=NOW - timedelta(seconds=6))
    assert evaluate(item).reason_code == "SOURCE_MESSAGE_STALE"


def test_receive_timestamp_in_future_fails_closed():
    item = evidence(received_at=NOW + timedelta(milliseconds=1))
    assert evaluate(item).reason_code == "RECEIVE_TIME_IN_FUTURE"


def test_impossible_future_source_timestamp_fails_closed():
    item = evidence(source_event_time=NOW + timedelta(seconds=10),
                    received_at=NOW - timedelta(seconds=1))
    assert evaluate(item).reason_code == "SOURCE_EVENT_TIME_IN_FUTURE"


def test_naive_timestamps_fail_closed():
    item = evidence(received_at=datetime(2026, 10, 11, 12, 0))
    assert evaluate(item).reason_code == "TIMESTAMP_TIMEZONE_REQUIRED"


def test_invalid_freshness_policy_fails_closed():
    assert evaluate(evidence(), max_age_seconds=-1).reason_code == "FRESHNESS_POLICY_INVALID"


def test_health_evidence_does_not_claim_sequence_semantics():
    # Health is only a transport/schema freshness result, not a sequence-contract verdict.
    result = evaluate(evidence())
    assert result.healthy
    assert result.reason_code == "SOURCE_MESSAGE_FRESH_AND_VALID"
