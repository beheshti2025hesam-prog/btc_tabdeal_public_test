from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from forward.evidence_lineage_contract_v1 import (
    EvidenceLineageError,
    verify_lineage,
)


def _seal(event):
    body = {key: value for key, value in event.items() if key != "event_sha256"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    event["event_sha256"] = hashlib.sha256(raw).hexdigest()
    return event


def valid_chain():
    start = datetime(2026, 10, 13, tzinfo=timezone.utc)
    session = _seal({
        "event_id": "evt-session", "event_type": "SESSION_STARTED",
        "session_id": "sess-1", "execution_id": None, "probe_id": None,
        "parent_event_id": None, "at_utc": start.isoformat(),
    })
    execution = _seal({
        "event_id": "evt-execution", "event_type": "EXECUTION_STARTED",
        "session_id": "sess-1", "execution_id": "exec-1", "probe_id": None,
        "parent_event_id": "evt-session", "at_utc": (start + timedelta(seconds=1)).isoformat(),
    })
    probe = _seal({
        "event_id": "evt-probe", "event_type": "PROBE_RECORDED",
        "session_id": "sess-1", "execution_id": "exec-1", "probe_id": "probe-1",
        "parent_event_id": "evt-execution", "at_utc": (start + timedelta(seconds=2)).isoformat(),
    })
    exit_event = _seal({
        "event_id": "evt-exit", "event_type": "EXIT_RECORDED",
        "session_id": "sess-1", "execution_id": "exec-1", "probe_id": "probe-1",
        "parent_event_id": "evt-probe", "at_utc": (start + timedelta(seconds=3)).isoformat(),
        "exit_event_id": "evt-exit",
    })
    return [session, execution, probe, exit_event]


def reseal(chain, index):
    event = chain[index]
    body = {key: value for key, value in event.items() if key != "event_sha256"}
    event["event_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def test_explicit_four_stage_lineage_is_accepted():
    assert verify_lineage(valid_chain()) == {
        "session_id": "sess-1", "execution_id": "exec-1",
        "probe_id": "probe-1", "exit_event_id": "evt-exit",
    }


@pytest.mark.parametrize(
    ("index", "field", "value", "error"),
    [
        (2, "execution_id", "exec-other", "PROBE_PARENT_MISMATCH"),
        (3, "probe_id", "probe-other", "EXIT_LINEAGE_MISMATCH"),
        (3, "parent_event_id", "evt-session", "EXIT_PARENT_MISMATCH"),
        (3, "exit_event_id", "forged-exit", "EXIT_EVENT_ID_MISMATCH"),
        (1, "parent_event_id", "missing-session", "EXECUTION_PARENT_MISMATCH"),
        (0, "session_id", "forged-session", "SESSION_LINEAGE_MISMATCH"),
    ],
)
def test_resealed_but_wrong_lineage_is_rejected(index, field, value, error):
    chain = valid_chain()
    chain[index][field] = value
    reseal(chain, index)
    with pytest.raises(EvidenceLineageError, match=error):
        verify_lineage(chain)


def test_payload_tampering_without_resealing_is_rejected():
    chain = valid_chain()
    chain[2]["probe_id"] = "tampered"
    with pytest.raises(EvidenceLineageError, match="EVENT_DIGEST_MISMATCH"):
        verify_lineage(chain)


def test_reordered_events_are_rejected():
    chain = valid_chain()
    with pytest.raises(EvidenceLineageError, match="EVENT_ORDER_INVALID"):
        verify_lineage([chain[0], chain[2], chain[1], chain[3]])


def test_duplicate_event_ids_are_rejected_even_when_hashes_are_valid():
    chain = valid_chain()
    chain[3]["event_id"] = chain[2]["event_id"]
    chain[3]["exit_event_id"] = chain[2]["event_id"]
    reseal(chain, 3)
    with pytest.raises(EvidenceLineageError, match="EVENT_ID_DUPLICATE"):
        verify_lineage(chain)


def test_naive_timestamp_is_rejected():
    chain = valid_chain()
    chain[1]["at_utc"] = "2026-10-13T00:00:01"
    reseal(chain, 1)
    with pytest.raises(EvidenceLineageError, match="TIMESTAMP_TIMEZONE_REQUIRED"):
        verify_lineage(chain)


def test_timestamp_regression_is_rejected():
    chain = valid_chain()
    chain[2]["at_utc"] = "2026-10-12T23:00:00+00:00"
    reseal(chain, 2)
    with pytest.raises(EvidenceLineageError, match="EVENT_TIME_REGRESSION"):
        verify_lineage(chain)


def test_incomplete_chain_is_rejected():
    with pytest.raises(EvidenceLineageError, match="LINEAGE_EVENT_COUNT_INVALID"):
        verify_lineage(valid_chain()[:3])
