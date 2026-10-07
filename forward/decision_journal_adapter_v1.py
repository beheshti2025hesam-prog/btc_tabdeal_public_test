"""Explicit adapter from DecisionResult to the forward journal contract."""

from __future__ import annotations


def decision_to_journal_record_v1(
    decision,
    *,
    event_id: str,
    evidence_source,
    market_input=None,
    candidate=None,
    confirmation=None,
    risk=None,
):
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if not isinstance(evidence_source, (str, list, tuple)):
        raise ValueError("evidence_source must be str/list/tuple")

    value = getattr(decision, "decision", None)
    if value not in ("LONG", "SHORT", "NO_TRADE"):
        raise ValueError("invalid decision")
    observed_at = getattr(decision, "observed_at", None)
    if observed_at is None:
        raise ValueError("observed_at is required")
    future_outcome = getattr(decision, "outcome", None)
    if future_outcome is not None:
        raise ValueError("DECISION_CONTAINS_FUTURE_OUTCOME")
    if getattr(decision, "closed_at", None) is not None:
        raise ValueError("DECISION_CONTAINS_FUTURE_CLOSED_AT")

    market_input = market_input or {}
    reasons = tuple(getattr(decision, "reason_codes", ()) or ())

    return {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": market_input.get("symbol"),
        "timeframe": market_input.get("timeframe"),
        "market_regime": market_input.get("market_regime"),
        "direction": value if value in ("LONG", "SHORT") else "NONE",
        "signal_state": getattr(candidate, "state", None),
        "confirmation_state": getattr(confirmation, "state", None),
        "risk_state": getattr(risk, "state", None),
        "decision": value,
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "rr": None,
        "quality_score": getattr(decision, "quality_score", None),
        "no_trade_reason": "|".join(reasons) if value == "NO_TRADE" else None,
        "outcome": None,
        "closed_at": None,
        "evidence_source": evidence_source,
    }
