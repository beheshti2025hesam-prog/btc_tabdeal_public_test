"""Forward-only strategy-family shadow lane. Paper candidates only; never authorizes orders."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .global_market_data_reader_v1 import MarketDataRejected
from .universal_indicator_engine_v1 import build_snapshot
from .indicator_strategy_family_v1 import evaluate_indicator_family, geometry
from .strategy_gate_pipeline_v1 import evaluate_confirmation_evidence, evaluate_risk_evidence
from .strategy_family_router_v1 import route_strategy_family

LANE_VERSION = "hes-strategy-family-paper-lane-v1.0.0"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
TIMEFRAMES = ("15m", "1h", "4h")
_NEWS_VETOES = {
    "HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION", "NEWS_TIMESTAMP_SUSPECT",
    "NEWS_TIMESTAMP_INVALID", "NEWS_TIMESTAMP_UNVERIFIED", "NEWS_SOURCE_UNVERIFIED",
    "NEWS_SOURCE_COVERAGE_INCOMPLETE", "NEWS_CONTEXT_NOT_READY",
}


@dataclass(frozen=True)
class _FamilyProposal:
    policy_version: str
    decision: str
    direction: str
    quality_score: int
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    reasons: tuple[str, ...]
    checks: Mapping[str, str]
    execution_enabled: bool = False
    orders_placed: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return sha256(raw).hexdigest()


def _normalized_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("closed") is not True:
            raise MarketDataRejected("FAMILY_LANE_REQUIRES_CLOSED_CANDLES")
        try:
            item = {
                "timestamp": int(row["open_time"]),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]), "quote_volume": float(row["quote_volume"]),
                "closed": True,
            }
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MarketDataRejected("FAMILY_LANE_INVALID_CANDLE_FIELDS") from exc
        if not all(v > 0 for k, v in item.items() if k in ("open", "high", "low", "close")):
            raise MarketDataRejected("FAMILY_LANE_INVALID_OHLC")
        if item["volume"] < 0 or item["quote_volume"] < 0:
            raise MarketDataRejected("FAMILY_LANE_INVALID_VOLUME")
        out.append(item)
    if len(out) < 220:
        raise MarketDataRejected("FAMILY_LANE_INSUFFICIENT_CLOSED_CANDLES")
    return out


def evaluate_strategy_family_paper_lane(
    *, data: Mapping[str, Any], structure: Mapping[str, Any], observed_at: datetime,
    precision_entry_1m: Mapping[str, Any], news_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate and independently gate shadow candidates from the canonical market snapshot."""
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("FAMILY_LANE_OBSERVED_AT_MUST_BE_TIMEZONE_AWARE")
    observed_at = observed_at.astimezone(timezone.utc)
    if data.get("source") != SOURCE or data.get("symbol") != SYMBOL:
        return _blocked("NON_CANONICAL_MARKET_IDENTITY")
    rows_by_tf = data.get("timeframes")
    if not isinstance(rows_by_tf, Mapping) or any(tf not in rows_by_tf for tf in TIMEFRAMES):
        return _blocked("REQUIRED_TIMEFRAMES_MISSING")

    try:
        snapshots = {
            tf: build_snapshot(
                _normalized_rows(list(rows_by_tf[tf])), venue="gateio", market="spot",
                symbol=SYMBOL, timeframe=tf, volume_semantics_qualified=True,
            )
            for tf in TIMEFRAMES
        }
    except (MarketDataRejected, TypeError, ValueError) as exc:
        return _blocked(str(exc)[:128])

    indicator_regimes = {tf: snapshots[tf].regime.label for tf in TIMEFRAMES}
    last_close = float(rows_by_tf["15m"][-1]["close"])
    indicator_candidates = evaluate_indicator_family(
        snapshots["15m"], snapshots["1h"], snapshots["4h"], close=last_close,
    )
    # The legacy indicator-family range variant is not the accepted Range v2
    # contract. Never promote it into the Mother candidate path.
    candidates = [c for c in indicator_candidates if c.variant_id in ("trend_confirmation", "momentum_breakout")]
    range_research = {
        "status": "RESEARCH_ONLY_NOT_PROMOTED",
        "reason_codes": ["DEDICATED_RANGE_ENGINE_V2_REQUIRED", "NO_MOTHER_CANDIDATE_AUTHORITY"],
        "legacy_indicator_variant_observed": any(c.variant_id == "range_mean_reversion" for c in indicator_candidates),
        "candidate_generation_authorized": False,
        "decision_authority": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    news = news_context if isinstance(news_context, Mapping) else {}
    news_status = str(news.get("status") or "BLOCKED")
    supplied_vetoes = news.get("veto_flags", [])
    vetoes = sorted(set(x for x in supplied_vetoes if isinstance(x, str) and x in _NEWS_VETOES)) if isinstance(supplied_vetoes, (list, tuple)) else []
    if news_status != "READY":
        vetoes = sorted(set((*vetoes, "NEWS_CONTEXT_NOT_READY")))

    rows = []
    for candidate in candidates:
        risk_geometry = geometry(candidate, last_close)
        if risk_geometry is None:
            continue
        route_regime = {"BULLISH": "UPTREND", "BEARISH": "DOWNTREND"}.get(candidate.regime, candidate.regime)
        route = route_strategy_family(
            source=SOURCE, symbol=SYMBOL, timeframe="15m", regime=route_regime,
        ).as_dict()
        parent_family = (
            "range_mean_reversion" if candidate.variant_id == "range_mean_reversion"
            else "trend_breakout"
        )
        proposal = _FamilyProposal(
            policy_version=candidate.family_version,
            decision=candidate.direction, direction=candidate.direction,
            quality_score=100, entry=risk_geometry["entry"],
            stop_loss=risk_geometry["stop_loss"], take_profit=risk_geometry["take_profit"],
            rr=risk_geometry["rr"], reasons=tuple(candidate.reason_codes),
            checks={"indicator_family": "PASS", "htf_alignment": "PASS", "closed_candles": "PASS"},
        )
        confirmation_bundle = evaluate_confirmation_evidence(
            proposal=proposal, structure=structure, source=SOURCE, symbol=SYMBOL,
            observed_at=observed_at,
        )
        base_confirmation = confirmation_bundle["confirmation"]
        confirmation_state = base_confirmation.state
        confirmation_reasons = list(base_confirmation.reason_codes)
        if vetoes:
            confirmation_state = "UNCONFIRMED"
            confirmation_reasons = list(dict.fromkeys((*confirmation_reasons, *vetoes)))
        # Risk is evaluated with the news-vetoed confirmation, never the pre-veto state.
        risk_confirmation = type("RiskConfirmation", (), {
            "state": confirmation_state,
            "reason_codes": tuple(confirmation_reasons),
        })()
        risk_bundle = evaluate_risk_evidence(
            proposal=proposal, confirmation=risk_confirmation, observed_at=observed_at,
        )
        precision_ready = precision_entry_1m.get("status") == "READY"
        if vetoes:
            status = "BLOCKED_NEWS_VETO"
        elif confirmation_state not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
            status = "BLOCKED_CONFIRMATION"
        elif risk_bundle["risk"].state != "RISK_APPROVED":
            status = "BLOCKED_RISK"
        elif not precision_ready:
            status = "WAITING_FOR_1M_PRECISION"
        else:
            status = "CONFIRMED_RISK_APPROVED_PAPER_ONLY"
        event_id = "family-paper:" + _hash({
            "source": SOURCE, "symbol": SYMBOL, "timeframe": "15m",
            "observed_at": candidate.observed_at, "variant": candidate.variant_id,
            "direction": candidate.direction, "version": candidate.family_version,
        })[:32]
        rows.append({
            "schema": "hes_strategy_family_paper_candidate_v1",
            "event_id": event_id,
            "lane_version": LANE_VERSION,
            "status": status,
            "paper_lane_activation_state": "PAPER_SHADOW_ACTIVE",
            "live_activation_state": route.get("activation_state"),
            "family_id": candidate.family_id,
            "family_version": candidate.family_version,
            "parent_family_id": parent_family,
            "variant_id": candidate.variant_id,
            "direction": candidate.direction,
            "market_regime": candidate.regime,
            "indicator_regimes": indicator_regimes,
            "source": SOURCE, "symbol": SYMBOL, "setup_timeframe": "15m",
            "precision_timeframe": "1m", "observed_at": observed_at.isoformat(),
            "candidate_observed_at": candidate.observed_at,
            "reference_price": risk_geometry["entry"],
            "entry_semantics": "CLOSED_15M_REFERENCE_NOT_EXECUTION_FILL",
            "stop_loss": risk_geometry["stop_loss"],
            "take_profit": risk_geometry["take_profit"], "rr": risk_geometry["rr"],
            "reason_codes": list(candidate.reason_codes),
            "strategy_family_route": route,
            "confirmation": {
                "state": confirmation_state, "reason_codes": confirmation_reasons,
                "passed_count": base_confirmation.passed_count,
                "required_count": base_confirmation.required_count,
                "checks": [
                    {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref}
                    for c in base_confirmation.checks
                ],
            },
            "risk": {
                "state": risk_bundle["risk"].state,
                "reason_codes": list(risk_bundle["risk"].reason_codes),
                "checks": [
                    {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref}
                    for c in risk_bundle["risk"].checks
                ],
                "simulation_only": True,
                "sizing": ({"approved": risk_bundle["sizing"].approved,
                            "quantity": risk_bundle["sizing"].quantity,
                            "notional_usdt": risk_bundle["sizing"].notional,
                            "risk_budget_usdt": risk_bundle["sizing"].risk_budget}
                           if risk_bundle["sizing"] else None),
            },
            "news_context_status": news_status, "news_veto_flags": vetoes,
            "precision_entry_1m_ready": precision_ready,
            "paper_candidate_generation_authorized": True,
            "decision_authority": False, "risk_gate_bypass": False,
            "execution_enabled": False, "orders_placed": False,
            "capital_mutated": False, "venue_adapter_called": False,
            "position_created": False, "future_outcomes_used": False,
        })

    if not rows:
        return {
            "schema": "hes_strategy_family_paper_lane_v1", "lane_version": LANE_VERSION,
            "status": "NO_CANDIDATE", "paper_lane_activation_state": "PAPER_SHADOW_ACTIVE",
            "reason_codes": ["NO_TREND_FAMILY_CANDIDATE"],
            "candidate_count": 0, "candidates": [], "selected_candidate": None,
            "indicator_regimes": indicator_regimes,
            "research_families": {"range_mean_reversion": range_research},
            "paper_candidate_generation_authorized": True, "decision_authority": False,
            "execution_enabled": False, "orders_placed": False,
        }
    selected = rows[0] if len(rows) == 1 else None
    lane_status = selected["status"] if selected else "MULTIPLE_CANDIDATES_REVIEW_REQUIRED"
    return {
        "schema": "hes_strategy_family_paper_lane_v1", "lane_version": LANE_VERSION,
        "status": lane_status, "paper_lane_activation_state": "PAPER_SHADOW_ACTIVE",
        "reason_codes": list(selected["reason_codes"]) if selected else ["MULTIPLE_CANDIDATES_REVIEW_REQUIRED"],
        "candidate_count": len(rows), "candidates": rows, "selected_candidate": selected,
        "indicator_regimes": indicator_regimes,
        "research_families": {"range_mean_reversion": range_research},
        "paper_candidate_generation_authorized": True, "decision_authority": False,
        "execution_enabled": False, "orders_placed": False,
    }


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema": "hes_strategy_family_paper_lane_v1", "lane_version": LANE_VERSION,
        "status": "BLOCKED", "reason_codes": [reason], "candidate_count": 0,
        "candidates": [], "selected_candidate": None,
        "paper_candidate_generation_authorized": False, "decision_authority": False,
        "execution_enabled": False, "orders_placed": False,
    }
