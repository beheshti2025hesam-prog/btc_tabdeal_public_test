from __future__ import annotations

import time
from dataclasses import dataclass

from core.orchestration.mother_supervisor_v1 import SpecialistSupervisorV1
from core.orchestration.mother_runtime_specialists_v1 import (
    LiveMarketContextV1,
    SupervisedRuntimeSpecialistV1,
    live_specialists_v1,
)
from core.orchestration.mother_v1 import AgentResult, MotherOrchestratorV1


EVIDENCE = "a" * 64
SNAPSHOT = "b" * 64
CONTEXT = {
    "scope": {"venue": "gateio", "product": "spot", "symbol": "BTC_USDT", "timeframe": "15m"},
    "observed_at": "2026-11-17T18:00:00+00:00",
    "snapshot_sha256": SNAPSHOT,
    "evidence_sha256": EVIDENCE,
    "request_id": "mother-supervisor-test-request",
}


@dataclass
class StatefulMarket:
    root: str = "/tmp/hes-test-market"
    observed_at: str = "2026-11-17T18:00:00+00:00"
    now_s: int = 1794938400
    journal_path: str = "/tmp/hes-test-journal.jsonl"
    _loaded: bool = True
    snapshot_sha256: str = SNAPSHOT
    count: int = 0


class StatefulSpecialist:
    def __init__(self, name: str, market: StatefulMarket, state: str = "PASS", delay: float = 0.0):
        self.name = name
        self.market = market
        self.state = state
        self.delay = delay
        self.VERSION = "test-specialist-v1"

    def evaluate(self, context):
        if self.delay:
            time.sleep(self.delay)
        self.market.count += 1
        payload = {"decision": "LONG"} if self.name == "decision" else {"count": self.market.count}
        return AgentResult(
            self.name, self.state, (), ("evidence:" + context["evidence_sha256"],),
            payload, self.VERSION,
        )


def test_supervised_specialist_round_trips_shared_market_state():
    supervisor = SpecialistSupervisorV1()
    market = StatefulMarket()
    first = SupervisedRuntimeSpecialistV1(StatefulSpecialist("market_structure", market), supervisor)
    second = SupervisedRuntimeSpecialistV1(StatefulSpecialist("signal", market), supervisor)

    result_a = first.evaluate(CONTEXT)
    result_b = second.evaluate(CONTEXT)

    assert result_a.state == "PASS"
    assert result_b.state == "PASS"
    assert market.count == 2


def test_supervised_duplicate_reuses_same_result_without_reexecuting():
    supervisor = SpecialistSupervisorV1()
    market = StatefulMarket()
    adapter = SupervisedRuntimeSpecialistV1(StatefulSpecialist("signal", market), supervisor)

    first = adapter.evaluate(CONTEXT)
    replay = adapter.evaluate(CONTEXT)

    assert first == replay
    assert market.count == 1


def test_timeout_maps_to_unknown_and_does_not_mutate_parent_market():
    supervisor = SpecialistSupervisorV1(kill_grace_seconds=0.05)
    market = StatefulMarket()
    adapter = SupervisedRuntimeSpecialistV1(
        StatefulSpecialist("signal", market, delay=1.0), supervisor, timeout_seconds=0.1
    )

    result = adapter.evaluate(CONTEXT)

    assert result.state == "UNKNOWN"
    assert "SPECIALIST_TIMEOUT" in result.reason_codes
    assert market.count == 0


def test_timeout_blocks_mother_and_never_authorizes_execution():
    supervisor = SpecialistSupervisorV1(kill_grace_seconds=0.05)
    market = StatefulMarket()
    states = {
        "data_quality": "PASS",
        "market_structure": "PASS",
        "signal": "PASS",
        "confirmation": "CONFIRMED",
        "risk": "APPROVED",
        "decision": "DECIDED",
        "evaluation": "OBSERVED",
    }
    agents = {}
    for name, state in states.items():
        delay = 1.0 if name == "market_structure" else 0.0
        agents[name] = SupervisedRuntimeSpecialistV1(
            StatefulSpecialist(name, market, state=state, delay=delay),
            supervisor,
            timeout_seconds=0.1,
        )

    result = MotherOrchestratorV1(agents).run(CONTEXT)

    assert result.decision == "NO_TRADE"
    assert result.execution_authorized is False
    assert result.stages[1].state == "UNKNOWN"
    assert len(result.stages) == 7


def test_supervised_factory_wraps_all_seven_canonical_runtime_specialists():
    supervisor = SpecialistSupervisorV1()
    market = LiveMarketContextV1(data_root="/tmp/hes-supervisor-factory-test")

    agents = live_specialists_v1(market, supervisor=supervisor)

    assert tuple(agents) == (
        "data_quality", "market_structure", "signal", "confirmation",
        "risk", "decision", "evaluation",
    )
    assert all(isinstance(agent, SupervisedRuntimeSpecialistV1) for agent in agents.values())


def test_supervisor_enforces_configured_per_specialist_parallelism():
    supervisor = SpecialistSupervisorV1(max_concurrent_per_agent=2)
    results = []
    import threading
    first = threading.Thread(target=lambda: results.append(
        supervisor.execute("signal", "parallel-1", time.sleep, 0.4, timeout_seconds=2.0)
    ))
    second = threading.Thread(target=lambda: results.append(
        supervisor.execute("signal", "parallel-2", time.sleep, 0.4, timeout_seconds=2.0)
    ))
    first.start()
    deadline = time.monotonic() + 3
    while supervisor.health()["active_counts"].get("signal", 0) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    second.start()
    deadline = time.monotonic() + 3
    while supervisor.health()["active_counts"].get("signal", 0) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    busy = supervisor.execute("signal", "parallel-3", time.sleep, 0.1, timeout_seconds=1.0)
    first.join(5)
    second.join(5)

    assert busy.status == "BUSY"
    assert len(results) == 2 and all(result.status == "SUCCEEDED" for result in results)
    assert supervisor.health()["active_counts"] == {}
