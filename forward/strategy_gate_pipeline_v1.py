"""Evidence-backed, forward-only gate orchestration. Observation-only; never executes orders."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from .market_structure_v1 import SwingPoint, infer_regime
from .candle_normalizer_v1 import Candle15m
from .structure_policy_v1 import confirm_swings_v1, label_confirmed_swings_v1, build_structure_events_v1
from .opportunity_policy_v1 import OpportunityPolicyV1
from .opportunity_detector_v1 import OpportunityDetectorV1
from core.risk.position_sizing import PositionSizingInput, size_position
import json
from pathlib import Path
from .opportunity_detector_v1 import OpportunityCandidate
from .confirmation_engine_v1 import ConfirmationCheck, ConfirmationEngineV1
from .confirmation_policy_v1 import ConfirmationPolicyV1
from .risk_gate_v1 import RiskCheck, RiskGateV1
from .risk_policy_v1 import RiskPolicyV1
from .strategy_family_router_v1 import route_strategy_family
from .strategy_family_context_v1 import build_strategy_family_context, verify_strategy_family_context

PIPELINE_VERSION = "hes-strategy-gate-pipeline-v1.0.2"

def _dt(value: Any) -> datetime:
    if isinstance(value, datetime): return value.astimezone(timezone.utc)
    if isinstance(value, (int,float)): return datetime.fromtimestamp(value, timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)

def inspect_structure(rows, observed_at):
    """Use the versioned causal swing policy; only contiguous, closed 15m candles count."""
    obs=_dt(observed_at)
    candles=[]
    for i,row in enumerate(rows):
        close_time=_dt(row["close_time"]); open_time=_dt(row["open_time"])
        if close_time > obs or row.get("closed") is False:
            continue
        candles.append(Candle15m("BTC_USDT","15m",open_time,close_time,
            Decimal(str(row["open"])),Decimal(str(row["high"])),Decimal(str(row["low"])),
            Decimal(str(row["close"])),Decimal(str(row.get("volume",0))),0,i,i,open_time,close_time))
    swings=confirm_swings_v1(candles,observed_at=obs)
    labeled=label_confirmed_swings_v1(swings)
    labels=[label for _,label in labeled if label != "UNCLASSIFIED"]
    regime=infer_regime(labels)
    events=build_structure_events_v1(swings,observed_at=obs)
    # Expose only concrete directional BOS/CHOCH events; ambiguous None events stay diagnostic.
    directional=[]
    for e in events:
        if e.event in ("BOS","CHOCH") and e.direction in ("BULLISH","BEARISH"):
            directional.append((e.event,e.direction))
    last_high=next((x for x in reversed(swings) if x.kind=="SWING_HIGH"),None)
    last_low=next((x for x in reversed(swings) if x.kind=="SWING_LOW"),None)
    event_names=[f"{kind}_{direction}" for kind,direction in directional]
    return {"observed_at":obs.isoformat(),"status":"OBSERVED" if swings else "UNKNOWN",
            "regime":regime,"labels":labels[-8:],"swing_count":len(swings),
            "last_swing_high":str(last_high.price) if last_high else None,
            "last_swing_low":str(last_low.price) if last_low else None,
            "events":event_names,"policy_note":"Versioned causal swing policy; pivot requires two right-side closed contiguous candles."}

def evaluate_confirmation_evidence(*, proposal, structure, source, symbol, observed_at):
    """Run the independent opportunity and confirmation specialists only."""
    obs = _dt(observed_at)
    direction = getattr(proposal, "direction", "NONE")
    regime = structure["regime"]
    candidate = OpportunityDetectorV1(OpportunityPolicyV1()).evaluate(
        observed_at=obs,
        symbol=symbol,
        timeframe="15m",
        regime=regime,
        structure_labels=structure["labels"],
        structure_events=structure["events"],
    )
    expected_direction = (
        "LONG" if candidate.state == "CANDIDATE_LONG"
        else "SHORT" if candidate.state == "CANDIDATE_SHORT"
        else "NONE"
    )
    aligned = direction == expected_direction and direction != "NONE"
    event_direction = expected_direction
    event_ok = (
        ("BOS_BULLISH" in structure["events"] or "CHOCH_BULLISH" in structure["events"])
        if event_direction == "LONG"
        else ("BOS_BEARISH" in structure["events"] or "CHOCH_BEARISH" in structure["events"])
        if event_direction == "SHORT"
        else False
    )
    candidate_ref = f"proposal_decision:{getattr(proposal, 'decision', 'UNKNOWN')};candidate:{candidate.state}"
    alignment_ref = f"proposal_direction:{direction};candidate_direction:{expected_direction};regime:{regime}"
    event_ref = f"candidate_direction:{expected_direction};matching_event_present:{event_ok}"
    checks = (
        ConfirmationCheck(
            "candidate_valid",
            "PASS" if candidate.state in ("CANDIDATE_LONG", "CANDIDATE_SHORT") else "FAIL",
            candidate_ref,
            obs,
        ),
        ConfirmationCheck(
            "direction_regime_alignment",
            "PASS" if aligned else "FAIL" if regime != "UNKNOWN" else "UNKNOWN",
            alignment_ref,
            obs,
        ),
        ConfirmationCheck(
            "structural_event_present",
            "PASS" if event_ok else "FAIL" if structure["status"] == "OBSERVED" else "UNKNOWN",
            event_ref,
            obs,
        ),
    )
    confirmation = ConfirmationEngineV1(ConfirmationPolicyV1()).evaluate(
        observed_at=obs, candidate=candidate, checks=checks
    )
    return {
        "candidate": candidate,
        "confirmation": confirmation,
        "expected_direction": expected_direction,
        "event_ok": event_ok,
    }


def evaluate_risk_evidence(*, proposal, confirmation, observed_at):
    """Run the independent bounded paper-risk specialist; never executes."""
    obs = _dt(observed_at)
    direction = getattr(proposal, "direction", "NONE")
    entry_value = getattr(proposal, "entry", None)
    stop_value = getattr(proposal, "stop_loss", None)
    target_value = getattr(proposal, "take_profit", None)
    geometry_ok = False
    rr_ok = False
    try:
        entry_decimal = Decimal(str(entry_value))
        stop_decimal = Decimal(str(stop_value))
        target_decimal = Decimal(str(target_value))
        if all(value.is_finite() and value > 0 for value in
               (entry_decimal, stop_decimal, target_decimal)):
            if direction == "LONG":
                geometry_ok = stop_decimal < entry_decimal < target_decimal
            elif direction == "SHORT":
                geometry_ok = target_decimal < entry_decimal < stop_decimal
            if geometry_ok:
                actual_rr = abs(target_decimal - entry_decimal) / abs(entry_decimal - stop_decimal)
                rr_ok = actual_rr >= Decimal("3.0")
    except (ArithmeticError, TypeError, ValueError):
        geometry_ok = False
        rr_ok = False

    cfg_path = Path(__file__).with_name("paper_risk_context_v1.json")
    cfg = json.loads(cfg_path.read_text()) if cfg_path.is_file() else {}
    sizing = None
    if (
        cfg.get("status") == "SIMULATION_ONLY_NOT_LIVE_APPROVAL"
        and direction in ("LONG", "SHORT")
        and entry_value
        and stop_value
    ):
        sizing = size_position(PositionSizingInput(
            equity=float(cfg["initial_simulated_equity_usdt"]),
            entry_price=float(proposal.entry),
            stop_price=float(proposal.stop_loss),
            side=direction,
            risk_fraction=float(cfg["risk_fraction_per_trade"]),
            fee_fraction_per_side=float(cfg["fee_fraction_per_side"]),
            slippage_fraction_per_side=float(cfg["slippage_fraction_per_side"]),
            max_notional_fraction=float(cfg["max_notional_fraction"]),
        ))
    risk_context_ok = bool(
        sizing and sizing.approved and cfg.get("leverage") == 1 and cfg.get("funding_cost_model")
    )
    risk_checks = (
        RiskCheck(
            "confirmation_valid",
            "PASS" if confirmation.state in ("CONFIRMED_LONG", "CONFIRMED_SHORT") else "FAIL",
            "confirmation:" + confirmation.state,
            obs,
        ),
        RiskCheck(
            "risk_context_available",
            "PASS" if risk_context_ok else "UNKNOWN",
            "simulation_config:" + str(cfg_path.name),
            obs,
        ),
        RiskCheck(
            "execution_disabled",
            "PASS" if cfg.get("safety", {}).get("live_execution_enabled") is False else "FAIL",
            "safety:live_execution_disabled",
            obs,
        ),
        RiskCheck(
            "portfolio_exposure",
            "PASS" if risk_context_ok else "UNKNOWN",
            "simulation_only:no_open_live_positions",
            obs,
        ),
        RiskCheck(
            "account_equity_and_sizing",
            "PASS" if risk_context_ok else "UNKNOWN",
            "simulation_equity_and_position_sizing",
            obs,
        ),
        RiskCheck(
            "execution_cost_model",
            "PASS" if risk_context_ok else "UNKNOWN",
            "assumption_based_fee_slippage; funding_not_modeled_for_spot_proxy",
            obs,
        ),
        RiskCheck(
            "entry_stop_target_geometry_valid",
            "PASS" if geometry_ok else "FAIL",
            "policy:entry-stop-target-directional-order",
            obs,
        ),
        RiskCheck(
            "risk_reward_gate_passed",
            "PASS" if rr_ok else "FAIL",
            "policy:minimum-3R",
            obs,
        ),
    )
    risk = RiskGateV1(RiskPolicyV1()).evaluate(
        observed_at=obs, confirmation=confirmation, checks=risk_checks
    )
    return {
        "risk": risk,
        "sizing": sizing,
        "config": cfg,
        "risk_context_ok": risk_context_ok,
        "geometry_ok": geometry_ok,
        "rr_ok": rr_ok,
    }


def evaluate_gate_evidence(*, proposal, rows_15m, frames, source, symbol, observed_at):
    """Compose the three independent specialists; never executes orders."""
    obs = _dt(observed_at)
    structure = inspect_structure(rows_15m, obs)
    confirmation_bundle = evaluate_confirmation_evidence(
        proposal=proposal, structure=structure, source=source, symbol=symbol, observed_at=obs
    )
    candidate = confirmation_bundle["candidate"]
    confirmation = confirmation_bundle["confirmation"]
    risk_bundle = evaluate_risk_evidence(
        proposal=proposal, confirmation=confirmation, observed_at=obs
    )
    risk = risk_bundle["risk"]
    sizing = risk_bundle["sizing"]
    cfg = risk_bundle["config"]

    # Family attribution is diagnostic metadata only. It cannot change the
    # candidate, confirmation, risk, or final-decision path below.
    family_route = route_strategy_family(
        source=source, symbol=symbol, timeframe="15m", regime=structure["regime"]
    ).as_dict()

    family_context = None
    family_context_status = "NOT_BUILT_NO_DIRECTIONAL_CANDIDATE"
    candidate_direction = (
        "LONG" if candidate.state == "CANDIDATE_LONG"
        else "SHORT" if candidate.state == "CANDIDATE_SHORT"
        else None
    )
    if family_route.get("family_id") and candidate_direction:
        candidate_payload = {
            "state": candidate.state,
            "observed_at": obs.isoformat(),
            "symbol": candidate.symbol,
            "timeframe": candidate.timeframe,
            "regime": candidate.regime,
            "structure_labels": list(candidate.structure_labels),
            "structure_events": list(candidate.structure_events),
            "reason_codes": list(candidate.reason_codes),
            "quality_score": candidate.quality_score,
        }
        gate_payload = {
            "strategy_family_route": family_route,
            "structure": structure,
            "confirmation": {
                "state": confirmation.state,
                "reason_codes": list(confirmation.reason_codes),
                "checks": [
                    {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                     "observed_at": c.observed_at.isoformat()}
                    for c in confirmation.checks
                ],
            },
            "risk": {
                "state": risk.state,
                "reason_codes": list(risk.reason_codes),
                "checks": [
                    {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                     "observed_at": c.observed_at.isoformat()}
                    for c in risk.checks
                ],
            },
        }
        try:
            built = build_strategy_family_context(
                source=source, symbol=symbol, timeframe="15m", regime=structure["regime"],
                direction=candidate_direction, observed_at=obs,
                candidate=candidate_payload, gate_evidence=gate_payload,
            )
            valid, invalid_reason = verify_strategy_family_context(built, now=obs)
            if valid:
                family_context = built
                family_context_status = "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED"
            else:
                family_context_status = "REJECTED:" + str(invalid_reason)
        except (TypeError, ValueError) as exc:
            family_context_status = "REJECTED:" + str(exc)[:120]

    return {
        "pipeline_version": PIPELINE_VERSION,
        "source": source,
        "symbol": symbol,
        "timeframe": "15m",
        "strategy_family_route": family_route,
        "strategy_family_context": family_context,
        "strategy_family_context_status": family_context_status,
        "structure": structure,
        "confirmation": {
            "state": confirmation.state,
            "passed_count": confirmation.passed_count,
            "required_count": confirmation.required_count,
            "reason_codes": list(confirmation.reason_codes),
            "checks": [
                {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                 "observed_at": c.observed_at.isoformat()}
                for c in confirmation.checks
            ],
        },
        "risk": {
            "state": risk.state,
            "reason_codes": list(risk.reason_codes),
            "checks": [
                {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                 "observed_at": c.observed_at.isoformat()}
                for c in risk.checks
            ],
        },
        "final_decision": "NO_TRADE",
        "execution_enabled": False,
        "orders_placed": False,
        "paper_risk_context": {
            "mode": "SIMULATION_ONLY_NOT_LIVE_APPROVAL",
            "sizing": (
                {
                    "approved": sizing.approved,
                    "quantity": sizing.quantity,
                    "notional_usdt": sizing.notional,
                    "risk_budget_usdt": sizing.risk_budget,
                    "estimated_stop_loss_usdt": sizing.estimated_stop_loss,
                    "estimated_round_trip_cost_usdt": sizing.estimated_round_trip_cost,
                    "reason": sizing.reason,
                }
                if sizing else None
            ),
            "assumption_notice": cfg.get("assumption_notice"),
        },
        "limitations": [
            "Risk sizing uses explicit simulation assumptions, not verified account or fee data",
            "Spot proxy does not model futures funding or leverage",
            "Live execution remains disabled; this evidence cannot authorize live orders",
        ],
    }
