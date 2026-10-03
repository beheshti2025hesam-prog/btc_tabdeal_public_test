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


@dataclass(frozen=True)
class RaceActorResult:
    actor: str
    claim_acquired: bool
    action: str


def simulate_claim_race(order: list[str]) -> list[RaceActorResult]:
    """Exercise the atomic claim boundary under adversarial actor ordering.

    Actors are intentionally limited to claim/reconcile actions; no GitHub API,
    workflow dispatch, or production collector is invoked by this harness.
    """
    store = DurableClaimStore()
    results: list[RaceActorResult] = []

    for actor in order:
        if actor == "normal":
            acquired = store.create_claim("N")
            results.append(
                RaceActorResult(
                    actor="normal",
                    claim_acquired=acquired,
                    action="claim" if acquired else "suppress_duplicate",
                )
            )
        elif actor == "watchdog":
            acquired = store.create_claim("N")
            results.append(
                RaceActorResult(
                    actor="watchdog",
                    claim_acquired=acquired,
                    action="claim" if acquired else "suppress_duplicate",
                )
            )
        else:
            raise ValueError(f"unknown actor: {actor}")

    return results


def test_adversarial_race_only_one_actor_can_claim_same_predecessor():
    for order in (["normal", "watchdog"], ["watchdog", "normal"]):
        results = simulate_claim_race(order)

        assert sum(result.claim_acquired for result in results) == 1
        assert [result.action for result in results].count("suppress_duplicate") == 1


def test_claim_race_cannot_create_two_successor_ids():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    assert store.create_claim("N") is False
    assert store.accept_dispatch(11111) is True
    assert store.accept_dispatch(22222) is False
    assert store.state == DurableHandoffState(
        state="dispatch_accepted",
        predecessor_run_id="N",
        successor_run_id=11111,
    )


def test_watchdog_cannot_turn_a_claimed_state_into_a_duplicate_dispatch():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    # A watchdog observing the claim before dispatch acceptance must fail closed.
    assert reconcile_durable_state(store.state, successor_visible=False) == "fail_closed"
    assert store.accept_dispatch(11111) is True
    assert reconcile_durable_state(store.state, successor_visible=False) == "await_visibility"


def test_reconciliation_is_stable_after_successor_becomes_visible():
    store = DurableClaimStore()

    assert store.create_claim("N") is True
    assert store.accept_dispatch(11111) is True

    observations = [
        reconcile_durable_state(store.state, successor_visible=False),
        reconcile_durable_state(store.state, successor_visible=True),
        reconcile_durable_state(store.state, successor_visible=True),
    ]

    assert observations == [
        "await_visibility",
        "suppress_duplicate",
        "suppress_duplicate",
    ]

@dataclass
class FakeActionsApi:
    """Branch-only API-contract double; never calls GitHub or a real workflow."""

    claim_created: bool = False
    state: str = "absent"
    successor_run_id: int | None = None
    successor_visible: bool = False

    def create_claim(self, predecessor_run_id: str) -> int:
        if self.claim_created:
            return 422
        self.claim_created = True
        self.state = "claimed"
        return 201

    def persist_acceptance(self, successor_run_id: int) -> int:
        if self.state != "claimed":
            return 409
        self.successor_run_id = successor_run_id
        self.state = "dispatch_accepted"
        return 200

    def dispatch(self) -> tuple[int, int]:
        if not self.claim_created:
            return 409, 0
        self.successor_run_id = 90001
        return 200, self.successor_run_id

    def get_successor(self) -> int:
        return 200 if self.successor_visible and self.successor_run_id is not None else 404


def test_api_contract_normal_handoff_is_claim_dispatch_accept_visible():
    api = FakeActionsApi()

    assert api.create_claim("N") == 201
    assert api.state == "claimed"

    dispatch_status, successor_run_id = api.dispatch()
    assert dispatch_status == 200
    assert successor_run_id == 90001

    assert api.persist_acceptance(successor_run_id) == 200
    assert api.state == "dispatch_accepted"

    assert api.get_successor() == 404
    api.successor_visible = True
    assert api.get_successor() == 200
    assert reconcile_durable_state(
        DurableHandoffState("dispatch_accepted", "N", successor_run_id),
        successor_visible=True,
    ) == "suppress_duplicate"


def test_api_contract_duplicate_claim_is_rejected_without_second_successor():
    api = FakeActionsApi()

    assert api.create_claim("N") == 201
    assert api.create_claim("N") == 422
    assert api.successor_run_id is None


def test_api_contract_claimed_without_acceptance_fails_closed():
    api = FakeActionsApi()

    assert api.create_claim("N") == 201
    assert reconcile_durable_state(
        DurableHandoffState("claimed", "N"),
        successor_visible=False,
    ) == "fail_closed"


def test_api_contract_accepted_but_not_visible_never_reissues_dispatch():
    api = FakeActionsApi()

    assert api.create_claim("N") == 201
    dispatch_status, successor_run_id = api.dispatch()
    assert (dispatch_status, successor_run_id) == (200, 90001)
    assert api.persist_acceptance(successor_run_id) == 200

    assert api.get_successor() == 404
    assert reconcile_durable_state(
        DurableHandoffState("dispatch_accepted", "N", successor_run_id),
        successor_visible=False,
    ) == "await_visibility"

    # Reconciliation observes the same accepted ID; it does not create a new one.
    assert api.successor_run_id == 90001
\n