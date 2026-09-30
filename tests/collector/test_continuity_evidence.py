"""Sample-level continuity evidence for completion-based collector handoff.

This harness is deliberately independent of the live collector. It validates the
boundary contract that a future production handoff artifact must satisfy:
last persisted event -> dispatch -> successor startup -> first event.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    sequence: int
    timestamp: datetime


@dataclass(frozen=True)
class HandoffEvidence:
    run_id: str
    predecessor_last: Event
    successor_first: Event
    dispatch_at: datetime
    successor_start_at: datetime


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def measure_gap(evidence: HandoffEvidence) -> float:
    """Return wall-clock gap in seconds between predecessor and successor events."""
    return (evidence.successor_first.timestamp - evidence.predecessor_last.timestamp).total_seconds()


def validate_handoff(evidence: HandoffEvidence) -> list[str]:
    """Return explicit invariant violations; an empty list means PASS."""
    errors: list[str] = []
    if evidence.successor_first.sequence <= evidence.predecessor_last.sequence:
        errors.append("successor sequence must be strictly greater than predecessor sequence")
    if evidence.dispatch_at < evidence.predecessor_last.timestamp:
        errors.append("dispatch cannot precede predecessor last-event timestamp")
    if evidence.successor_start_at < evidence.dispatch_at:
        errors.append("successor startup cannot precede dispatch")
    if evidence.successor_first.timestamp < evidence.successor_start_at:
        errors.append("successor first event cannot precede successor startup")
    if measure_gap(evidence) < 0:
        errors.append("negative event-time handoff gap")
    return errors


def test_sample_level_n_to_n_plus_1_handoff_has_measurable_boundary():
    evidence = HandoffEvidence(
        run_id="N->N+1",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:00.000Z")),
        dispatch_at=_utc("2026-09-30T00:00:00.400Z"),
        successor_start_at=_utc("2026-09-30T00:00:01.100Z"),
        successor_first=Event(1001, _utc("2026-09-30T00:00:01.700Z")),
    )

    assert validate_handoff(evidence) == []
    assert measure_gap(evidence) == 1.7


def test_sample_level_sequence_regression_is_fail_closed():
    evidence = HandoffEvidence(
        run_id="N->N+1-regression",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:00Z")),
        dispatch_at=_utc("2026-09-30T00:00:00.1Z"),
        successor_start_at=_utc("2026-09-30T00:00:00.2Z"),
        successor_first=Event(999, _utc("2026-09-30T00:00:00.3Z")),
    )

    errors = validate_handoff(evidence)
    assert "successor sequence must be strictly greater than predecessor sequence" in errors


def test_sample_level_negative_time_boundary_is_fail_closed():
    evidence = HandoffEvidence(
        run_id="N->N+1-negative-time",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:02Z")),
        dispatch_at=_utc("2026-09-30T00:00:02.1Z"),
        successor_start_at=_utc("2026-09-30T00:00:02.2Z"),
        successor_first=Event(1001, _utc("2026-09-30T00:00:01.9Z")),
    )

    errors = validate_handoff(evidence)
    assert "successor first event cannot precede successor startup" in errors
    assert "negative event-time handoff gap" in errors

def claim_successor_dispatch(claimed_predecessors: set[str], predecessor_run_id: str) -> bool:
    """Atomically model a durable one-successor claim."""
    if predecessor_run_id in claimed_predecessors:
        return False
    claimed_predecessors.add(predecessor_run_id)
    return True


def test_duplicate_successor_dispatch_is_idempotent_with_durable_marker():
    claims: set[str] = set()

    assert claim_successor_dispatch(claims, "N") is True
    assert claim_successor_dispatch(claims, "N") is False
    assert claims == {"N"}


@dataclass(frozen=True)
class DispatchReconciliation:
    claim_exists: bool
    successor_visible: bool
    dispatch_accepted: bool


def reconcile_dispatch(state: DispatchReconciliation) -> str:
    """Model the safe branch-level liveness rule without performing a dispatch."""
    if state.successor_visible:
        return "already_materialized"
    if not state.claim_exists:
        return "claim_required"
    if not state.dispatch_accepted:
        return "recoverable_dispatch_failure"
    return "await_visibility"


def test_claim_does_not_prove_dispatch_liveness():
    assert reconcile_dispatch(
        DispatchReconciliation(
            claim_exists=True,
            successor_visible=False,
            dispatch_accepted=False,
        )
    ) == "recoverable_dispatch_failure"


def test_visible_successor_suppresses_duplicate_recovery():
    assert reconcile_dispatch(
        DispatchReconciliation(
            claim_exists=True,
            successor_visible=True,
            dispatch_accepted=True,
        )
    ) == "already_materialized"


def test_claim_without_visible_successor_requires_reconciliation():
    assert reconcile_dispatch(
        DispatchReconciliation(
            claim_exists=True,
            successor_visible=False,
            dispatch_accepted=True,
        )
    ) == "await_visibility"


def test_missing_claim_is_not_dispatch_authorization():
    assert reconcile_dispatch(
        DispatchReconciliation(
            claim_exists=False,
            successor_visible=False,
            dispatch_accepted=False,
        )
    ) == "claim_required"


@dataclass(frozen=True)
class DurableHandoffState:
    state: str
    predecessor_run_id: str
    successor_run_id: int | None = None


def reconcile_durable_state(state: DurableHandoffState, successor_visible: bool) -> str:
    """Model watchdog decisions from the durable claim state only."""
    if state.state == "dispatch_accepted":
        if state.successor_run_id is None:
            return "fail_closed"
        return "suppress_duplicate" if successor_visible else "await_visibility"
    if state.state == "claimed":
        return "fail_closed"
    return "fail_closed"


def test_dispatch_accepted_visible_successor_suppresses_recovery():
    state = DurableHandoffState(
        state="dispatch_accepted",
        predecessor_run_id="N",
        successor_run_id=12345,
    )
    assert reconcile_durable_state(state, successor_visible=True) == "suppress_duplicate"


def test_dispatch_accepted_invisible_successor_waits_without_duplicate_dispatch():
    state = DurableHandoffState(
        state="dispatch_accepted",
        predecessor_run_id="N",
        successor_run_id=12345,
    )
    assert reconcile_durable_state(state, successor_visible=False) == "await_visibility"


def test_claimed_without_accepted_dispatch_fails_closed():
    state = DurableHandoffState(
        state="claimed",
        predecessor_run_id="N",
    )
    assert reconcile_durable_state(state, successor_visible=False) == "fail_closed"


def test_accepted_state_without_successor_id_fails_closed():
    state = DurableHandoffState(
        state="dispatch_accepted",
        predecessor_run_id="N",
    )
    assert reconcile_durable_state(state, successor_visible=False) == "fail_closed"


def test_unknown_durable_state_fails_closed():
    state = DurableHandoffState(
        state="unexpected",
        predecessor_run_id="N",
        successor_run_id=12345,
    )
    assert reconcile_durable_state(state, successor_visible=False) == "fail_closed"


@dataclass
class DurableClaimStore:
    """In-memory stand-in for the claim branch + state.json contract."""
    state: DurableHandoffState | None = None

    def create_claim(self, predecessor_run_id: str) -> bool:
        if self.state is not None:
            return False
        self.state = DurableHandoffState(
            state="claimed",
            predecessor_run_id=predecessor_run_id,
        )
        return True

    def accept_dispatch(self, successor_run_id: int) -> bool:
        if self.state is None or self.state.state != "claimed":
            return False
        self.state = DurableHandoffState(
            state="dispatch_accepted",
            predecessor_run_id=self.state.predecessor_run_id,
            successor_run_id=successor_run_id,
        )
        return True


def test_runtime_equivalent_claim_to_accepted_to_visible_flow_is_idempotent():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    assert store.state == DurableHandoffState(state="claimed", predecessor_run_id="N")
    assert reconcile_durable_state(store.state, successor_visible=False) == "fail_closed"

    assert store.accept_dispatch(12345) is True
    assert store.state == DurableHandoffState(
        state="dispatch_accepted",
        predecessor_run_id="N",
        successor_run_id=12345,
    )
    assert reconcile_durable_state(store.state, successor_visible=False) == "await_visibility"
    assert reconcile_durable_state(store.state, successor_visible=True) == "suppress_duplicate"

    # A second actor cannot acquire a new claim for the same predecessor.
    assert store.create_claim("N") is False
    # A second acceptance cannot rewrite an already accepted claim.
    assert store.accept_dispatch(67890) is False
    assert store.state.successor_run_id == 12345


def test_runtime_equivalent_dispatch_failure_never_auto_dispatches_from_claimed_state():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    assert store.state is not None
    assert reconcile_durable_state(store.state, successor_visible=False) == "fail_closed"
    assert store.state.state == "claimed"
    assert store.state.successor_run_id is None


def test_runtime_equivalent_accepted_but_eventually_invisible_successor_waits():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    assert store.accept_dispatch(54321) is True
    assert reconcile_durable_state(store.state, successor_visible=False) == "await_visibility"
    assert reconcile_durable_state(store.state, successor_visible=False) == "await_visibility"
    assert store.state.successor_run_id == 54321
