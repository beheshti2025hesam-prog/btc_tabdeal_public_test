from pathlib import Path
import tempfile

from forward.forward_journal_v1 import ForwardJournalV1


def _record(event_id="evt-1"):
    return {
        "event_id": event_id,
        "observed_at": "2026-10-07T01:00:00+00:00",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "market_regime": "UPTREND",
        "direction": "LONG",
        "signal_state": "CANDIDATE_PRESENT",
        "confirmation_state": "CONFIRMED_LONG",
        "risk_state": "RISK_APPROVED",
        "decision": "LONG",
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "rr": None,
        "quality_score": None,
        "no_trade_reason": None,
        "outcome": None,
        "closed_at": None,
        "evidence_source": "forward_pipeline_v1",
    }


def test_append_decision_and_duplicate_rejection():
    with tempfile.TemporaryDirectory() as d:
        journal = ForwardJournalV1(Path(d) / "journal.jsonl")
        journal.append_decision(_record())
        try:
            journal.append_decision(_record())
        except ValueError as exc:
            assert str(exc) == "duplicate event_id"
        else:
            raise AssertionError("duplicate event_id was accepted")
        assert len(journal.path.read_text(encoding="utf-8").splitlines()) == 1


def test_no_trade_is_first_class():
    with tempfile.TemporaryDirectory() as d:
        journal = ForwardJournalV1(Path(d) / "journal.jsonl")
        record = _record("evt-no-trade")
        record["decision"] = "NO_TRADE"
        record["direction"] = "NONE"
        record["no_trade_reason"] = "RISK_NOT_APPROVED"
        journal.append_decision(record)
        assert '"decision": "NO_TRADE"' in journal.path.read_text(encoding="utf-8")


def test_outcome_never_mutates_decision():
    with tempfile.TemporaryDirectory() as d:
        journal = ForwardJournalV1(Path(d) / "journal.jsonl")
        try:
            journal.append_outcome(
                event_id="evt-1",
                outcome="WIN",
                closed_at="2026-10-07T01:15:00+00:00",
            )
        except NotImplementedError:
            pass
        else:
            raise AssertionError("journal attempted outcome mutation")
