"""Integration tests for the complete forward runtime validation path."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from forward.forward_journal_v1 import ForwardJournalV1
from forward.forward_pipeline_v1 import ForwardPipelineV1, run_once
from forward.forward_run_controller_v1 import ForwardRunControllerV1
from forward.runtime_bridge_v1 import ForwardRuntimeBridgeV1


def _active_controller():
    return ForwardRunControllerV1(
        policy={
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "historical_performance_tuning_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        },
        ruleset={
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        },
    )


class _Decision:
    def __init__(self, decision="NO_TRADE", reason="RISK_NOT_APPROVED", outcome=None):
        self.decision = decision
        self.reason = reason
        self.outcome = outcome
        self.observed_at = "2026-10-07T05:00:00+00:00"

    def as_journal_record(self, event_id, evidence_source):
        return {
            "event_id": event_id,
            "observed_at": "2026-10-07T05:00:00+00:00",
            "symbol": "BTC_USDT",
            "timeframe": "15m",
            "market_regime": "UNKNOWN",
            "direction": "NONE",
            "signal_state": "CANDIDATE_PRESENT",
            "confirmation_state": "CONFIRMED_LONG",
            "risk_state": "RISK_REJECTED",
            "decision": self.decision,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "rr": None,
            "quality_score": None,
            "no_trade_reason": self.reason,
            "outcome": self.outcome,
            "closed_at": None,
            "evidence_source": evidence_source,
        }


def _runner(decision, journal):
    def runner(**kwargs):
        return run_once(
            market_input=kwargs["market_input"],
            structure_engine=lambda _: object(),
            opportunity_engine=lambda *_: object(),
            confirmation_engine=lambda *_: object(),
            risk_gate=lambda *_: object(),
            decision_engine=lambda *_: decision,
            journal=journal,
            event_id=kwargs["event_id"],
            evidence_source=kwargs["evidence_source"],
        )
    return runner


def test_valid_no_trade_flows_bridge_to_validated_journal():
    with tempfile.TemporaryDirectory() as d:
        journal = ForwardJournalV1(Path(d) / "journal.jsonl")
        bridge = ForwardRuntimeBridgeV1(
            controller=_active_controller(),
            pipeline=ForwardPipelineV1(runner=_runner(_Decision(), journal)),
        )
        result = bridge.process_input(
            run_id="FORWARD_E2E_VALID_001",
            observed_at=datetime.now(timezone.utc),
            market_input={"symbol": "BTC_USDT"},
            event_id="evt-valid-001",
            evidence_source="forward_e2e_test",
        )
        assert result.journal_record["decision"] == "NO_TRADE"
        assert journal.path.read_text(encoding="utf-8").count("\n") == 1


def test_future_outcome_is_rejected_before_journal_append():
    with tempfile.TemporaryDirectory() as d:
        journal = ForwardJournalV1(Path(d) / "journal.jsonl")
        bridge = ForwardRuntimeBridgeV1(
            controller=_active_controller(),
            pipeline=ForwardPipelineV1(
                runner=_runner(_Decision(outcome="WIN"), journal)
            ),
        )
        try:
            bridge.process_input(
                run_id="FORWARD_E2E_LEAK_001",
                observed_at=datetime.now(timezone.utc),
                market_input={"symbol": "BTC_USDT"},
                event_id="evt-leak-001",
                evidence_source="forward_e2e_test",
            )
        except ValueError as exc:
            assert "DECISION_CONTAINS_FUTURE_OUTCOME" in str(exc)
        else:
            raise AssertionError("future outcome was accepted")
        assert not journal.path.exists() or not journal.path.read_text(encoding="utf-8").strip()
