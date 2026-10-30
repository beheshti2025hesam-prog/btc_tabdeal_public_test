"""Signal Agent adapter to the canonical HES trade journal.

This deliberately reuses ForwardJournalV1 and trade_journal_v2.jsonl, which
are already consumed by the paper evaluator and strategy_learning_loop_v1.
It does not create a second journal, outcome ledger, or learning loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .forward_journal_v1 import ForwardJournalV1


@dataclass(frozen=True)
class JournalWriteResult:
    status: str
    event_id: str
    digest: str


def _digest(record: dict) -> str:
    return sha256(json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")).hexdigest()


def record_signal_decision(
    journal_path: str | Path,
    *,
    decision: str,
    observed_at: str,
    symbol: str,
    timeframe: str,
    source: str,
    product: str,
    response_sha256: str,
    htf_response_sha256: str,
    strategy_evidence_sha256: str | None,
    policy_version: str,
    status: str,
    market_regime: str,
    rejected_at: str,
    reason_codes: Iterable[str],
    direction: str = "NONE",
    signal_state: str = "UNKNOWN",
    confirmation_state: str = "UNKNOWN",
    risk_state: str = "UNKNOWN",
    entry: str | None = None,
    stop_loss: str | None = None,
    take_profit: str | None = None,
    rr: float | None = None,
    quality_score: float | None = None,
    proposal_decision: str = "UNKNOWN",
    structure_events: Iterable[str] = (),
    structure_labels: Iterable[str] = (),
    confirmation_reasons: Iterable[str] = (),
    risk_reasons: Iterable[str] = (),
) -> JournalWriteResult:
    """Append one immutable Signal Agent decision to the existing journal."""
    if decision not in {"LONG", "SHORT", "NO_TRADE"}:
        raise ValueError("invalid_decision")
    for name, value in (
        ("observed_at", observed_at), ("symbol", symbol), ("timeframe", timeframe),
        ("source", source), ("product", product), ("policy_version", policy_version),
        ("status", status), ("market_regime", market_regime),
        ("signal_state", signal_state), ("confirmation_state", confirmation_state),
        ("risk_state", risk_state),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_" + name)
    if direction not in {"LONG", "SHORT", "NONE", "UNKNOWN"}:
        raise ValueError("invalid_direction")
    if not isinstance(rejected_at, str):
        raise ValueError("invalid_rejected_at")
    for name, value in (("response_sha256", response_sha256), ("htf_response_sha256", htf_response_sha256)):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid_" + name)
    if strategy_evidence_sha256 is not None and (
        not isinstance(strategy_evidence_sha256, str) or len(strategy_evidence_sha256) != 64
        or any(c not in "0123456789abcdef" for c in strategy_evidence_sha256)
    ):
        raise ValueError("invalid_strategy_evidence_sha256")
    if isinstance(reason_codes, (str, bytes)):
        raise ValueError("invalid_reason_codes")
    reasons = list(reason_codes)
    structures = list(structure_events)
    labels = list(structure_labels)
    confirmation_codes = list(confirmation_reasons)
    risk_codes = list(risk_reasons)
    for values in (reasons, structures, labels, confirmation_codes, risk_codes):
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError("invalid_reason_codes")
    if not isinstance(proposal_decision, str) or not proposal_decision.strip():
        raise ValueError("invalid_proposal_decision")
    for name, value in (("entry", entry), ("stop_loss", stop_loss), ("take_profit", take_profit)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("invalid_" + name)

    # Identity is bound to the exact persisted source batches and policy version.
    # Re-polling the same closed-candle evidence cannot create duplicate decisions.
    identity = {
        "symbol": symbol, "timeframe": timeframe, "source": source, "product": product,
        "response_sha256": response_sha256, "htf_response_sha256": htf_response_sha256,
        "policy_version": policy_version,
    }
    identity_sha = _digest(identity)
    event_id = "hes-signal-" + identity_sha
    payload = {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "market_regime": market_regime,
        "direction": direction if direction in {"LONG", "SHORT"} else "NONE",
        "proposal_direction": direction if direction in {"LONG", "SHORT"} else "NONE",
        "proposal_decision": proposal_decision,
        "proposal_entry": entry,
        "proposal_stop_loss": stop_loss,
        "proposal_take_profit": take_profit,
        "proposal_rr": rr,
        "proposal_reasons": reasons,
        "signal_state": signal_state,
        "confirmation_state": confirmation_state,
        "risk_state": risk_state,
        "decision": decision,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": rr,
        "quality_score": quality_score,
        "no_trade_reason": "|".join(reasons) if decision == "NO_TRADE" and reasons else None,
        "outcome": None,
        "closed_at": None,
        "evidence_source": source,
        "source": source,
        "product": product,
        "response_sha256": response_sha256,
        "htf_response_sha256": htf_response_sha256,
        "strategy_evidence_sha256": strategy_evidence_sha256,
        "policy_version": policy_version,
        "decision_gate": rejected_at or "SIGNAL_AGENT",
        "rejected_at": rejected_at,
        "reason_codes": reasons,
        "gate_reasons": reasons,
        "gate_evidence": {
            "structure": {
                "status": "OBSERVED" if market_regime != "UNKNOWN" else "UNKNOWN",
                "regime": market_regime,
                "events": structures,
                "labels": labels,
            },
            "strategy": {"state": signal_state, "reason_codes": reasons},
            "confirmation": {"state": confirmation_state, "reason_codes": confirmation_codes},
            "risk": {"state": risk_state, "reason_codes": risk_codes},
            "execution_enabled": False,
            "orders_placed": False,
        },
        "execution_enabled": False,
        "orders_placed": False,
    }
    journal_path = Path(journal_path)
    try:
        ForwardJournalV1(journal_path).append_decision(payload)
        return JournalWriteResult("RECORDED", event_id, _digest(payload))
    except ValueError as exc:
        if str(exc) != "duplicate event_id":
            raise
        # The writer's lock makes duplicate detection atomic. Re-read the existing
        # record and accept only an identical decision; changed decisions fail closed.
        for line in journal_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("event_id") != event_id:
                continue
            comparable_existing = dict(existing)
            comparable_expected = dict(payload)
            for volatile in ("observed_at", "strategy_evidence_sha256"):
                comparable_existing.pop(volatile, None)
                comparable_expected.pop(volatile, None)
            if comparable_existing == comparable_expected:
                return JournalWriteResult("ALREADY_RECORDED", event_id, _digest(existing))
            raise ValueError("conflicting_duplicate_decision_event") from exc
        raise
