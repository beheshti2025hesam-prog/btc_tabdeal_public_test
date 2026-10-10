from datetime import datetime, timedelta, timezone

import pytest

from forward.source_health_evidence_v1 import evaluate_source_health, SCHEMA


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def evidence(**overrides):
    result = {
        "schema": SCHEMA,
        "venue": "tabdeal",
        "product": "futures",
        "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
        "topic": "trade",
        "expected_symbol": "BTC_USDT",
        "observed_symbol": "BTC_USDT",
        "connection_id": "conn-1",
        "session_id": "run-1",
        "session_generation": 1,
        "source_event_at_utc": (NOW - timedelta(seconds=2)).isoformat(),
        "received_at_utc": NOW.isoformat(),
        "freshness_bound_seconds": 5,
        "schema_validated": True,
        "schema_validation_reason": "SCHEMA_VALID",
        "reason_code": "SOURCE_HEALTHY",
    }
    result.update(overrides)
    return result


def evaluate(item):
    return evaluate_source_health(
        item, expected_run_id="run-1", expected_session_generation=1, now_utc=NOW
    )


def test_valid_fresh_scoped_evidence_is_healthy():
    assert evaluate(evidence()) == {
        "source_health": "HEALTHY", "reason_code": "SOURCE_HEALTHY"
    }


@pytest.mark.parametrize("change,reason", [
    ({"observed_symbol": "ETH_USDT"}, "SOURCE_HEALTH_SYMBOL_MISMATCH"),
    ({"topic": "ticker"}, "SOURCE_HEALTH_SCOPE_MISMATCH"),
    ({"venue": "other"}, "SOURCE_HEALTH_SCOPE_MISMATCH"),
    ({"session_id": "other-run"}, "SOURCE_HEALTH_SESSION_MISMATCH"),
    ({"session_generation": 2}, "SOURCE_HEALTH_SESSION_GENERATION_MISMATCH"),
    ({"schema_validated": False}, "SOURCE_SCHEMA_VALIDATION_FAILED"),
    ({"schema_validation_reason": "SCHEMA_INVALID"}, "SOURCE_HEALTH_SCHEMA_VALIDATION_CONTRADICTION"),
    ({"source_event_at_utc": "not-a-time"}, "SOURCE_HEALTH_TIMESTAMP_INVALID"),
    ({"source_event_at_utc": (NOW + timedelta(seconds=1)).isoformat()}, "SOURCE_EVENT_TIMESTAMP_IN_FUTURE"),
    ({"received_at_utc": (NOW - timedelta(seconds=10)).isoformat()}, "SOURCE_RECEIVE_TIMESTAMP_STALE_OR_FUTURE"),
    ({"source_event_at_utc": (NOW - timedelta(seconds=8)).isoformat()}, "SOURCE_STALE"),
    ({"freshness_bound_seconds": True}, "SOURCE_HEALTH_FRESHNESS_BOUND_INVALID"),
    ({"freshness_bound_seconds": float("inf")}, "SOURCE_HEALTH_FRESHNESS_BOUND_INVALID"),
    ({"reason_code": "SOURCE_STALE"}, "SOURCE_HEALTH_REASON_CONTRADICTION"),
])
def test_invalid_or_adversarial_evidence_is_unhealthy(change, reason):
    result = evaluate(evidence(**change))
    assert result == {"source_health": "UNHEALTHY", "reason_code": reason}


def test_missing_or_extra_fields_fail_closed():
    item = evidence()
    del item["connection_id"]
    assert evaluate(item)["reason_code"] == "SOURCE_HEALTH_EVIDENCE_SCHEMA_INVALID"
    item = evidence(untrusted_healthy=True)
    assert evaluate(item)["reason_code"] == "SOURCE_HEALTH_EVIDENCE_SCHEMA_INVALID"


def test_naive_timestamps_are_rejected():
    result = evaluate(evidence(source_event_at_utc="2026-10-10T11:59:58"))
    assert result["reason_code"] == "SOURCE_HEALTH_TIMESTAMP_INVALID"
