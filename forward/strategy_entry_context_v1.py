"""Provenance-bound 15m paper setup context consumed by the advisory 1m engine."""
from __future__ import annotations
import hashlib, json, math
from typing import Any, Mapping

SCHEMA = "hes_strategy_entry_context_v1"
ENTRY_ZONE_POLICY = "FAVORABLE_SIDE_RISK_FRACTION_V1"
ENTRY_ZONE_FRACTION_OF_RISK = 0.25

def _canonical_hash(value: Mapping[str, Any]) -> str:
    raw=json.dumps(dict(value),sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def build_entry_context(*, source: str, symbol: str, candidate_time: int, policy_version: str,
                        direction: str, entry: float, stop: float, target: float,
                        gate_evidence: Mapping[str, Any], ttl_seconds: int = 900) -> dict:
    """Build a one-15m-window context only after upstream paper eligibility has passed."""
    if source != "gateio_public_spot" or symbol != "BTC_USDT" or direction not in ("LONG","SHORT"):
        raise ValueError("ENTRY_CONTEXT_SCOPE_INVALID")
    if isinstance(candidate_time,bool) or not isinstance(candidate_time,int) or candidate_time<=0:
        raise ValueError("ENTRY_CONTEXT_TIME_INVALID")
    if not isinstance(ttl_seconds,int) or isinstance(ttl_seconds,bool) or ttl_seconds!=900:
        raise ValueError("ENTRY_CONTEXT_TTL_POLICY_INVALID")
    risk=gate_evidence.get("risk",{})
    confirmation=gate_evidence.get("confirmation",{})
    structure=gate_evidence.get("structure",{})
    if risk.get("state")!="RISK_APPROVED": raise ValueError("ENTRY_CONTEXT_RISK_NOT_APPROVED")
    if confirmation.get("state")!="CONFIRMED_"+direction: raise ValueError("ENTRY_CONTEXT_CONFIRMATION_MISMATCH")
    if structure.get("status")!="OBSERVED" or structure.get("regime") not in ("UPTREND","DOWNTREND"):
        raise ValueError("ENTRY_CONTEXT_STRUCTURE_NOT_DIRECTIONAL")
    if (direction=="LONG" and structure.get("regime")!="UPTREND") or (direction=="SHORT" and structure.get("regime")!="DOWNTREND"):
        raise ValueError("ENTRY_CONTEXT_STRUCTURE_DIRECTION_MISMATCH")
    entry=float(entry); stop=float(stop); target=float(target)
    if not all(math.isfinite(x) and x>0 for x in (entry,stop,target)):
        raise ValueError("ENTRY_CONTEXT_GEOMETRY_INVALID")
    if direction=="LONG" and not stop<entry<target: raise ValueError("ENTRY_CONTEXT_GEOMETRY_INVALID")
    if direction=="SHORT" and not target<entry<stop: raise ValueError("ENTRY_CONTEXT_GEOMETRY_INVALID")
    risk_distance=abs(entry-stop)
    rr=abs(target-entry)/risk_distance
    if rr<3.0: raise ValueError("ENTRY_CONTEXT_RR_BELOW_MINIMUM")
    zone_width=risk_distance*ENTRY_ZONE_FRACTION_OF_RISK
    if direction=="LONG":
        entry_zone_low,entry_zone_high=entry-zone_width,entry
    else:
        entry_zone_low,entry_zone_high=entry,entry+zone_width
    gate_payload={k:v for k,v in gate_evidence.items() if k!="entry_context"}
    base={
      "schema":SCHEMA,
      "setup_id":f"hes-setup-{symbol}-15m-{candidate_time}-{direction}",
      "source":"strategy_policy_v2","market_data_source":source,"symbol":symbol,"timeframe":"15m","direction":direction,
      "observed_at":candidate_time,"valid_until":candidate_time+ttl_seconds,
      "planned_entry_price":entry,
      "entry_zone_low":entry_zone_low,"entry_zone_high":entry_zone_high,
      "entry_zone_policy":ENTRY_ZONE_POLICY,
      "entry_zone_fraction_of_risk":ENTRY_ZONE_FRACTION_OF_RISK,
      "stop_price":stop,"target_price":target,"planned_rr":rr,
      "risk_gate_state":"RISK_APPROVED","confirmation_state":"CONFIRMED_"+direction,
      "market_regime":structure.get("regime"),"policy_version":policy_version,
      "gate_evidence_sha256":_canonical_hash(gate_payload),
      "setup_validated_15m":True,"execution_enabled":False,"orders_placed":False,
    }
    return {**base,"evidence_sha256":_canonical_hash(base)}

def verify_entry_context(context: Any, *, gate_evidence: Mapping[str, Any] | None = None, now_s: int,
                         expected_direction: str | None = None) -> tuple[bool,str | None]:
    if not isinstance(context,dict): return False,"ENTRY_CONTEXT_MISSING"
    if context.get("schema")!=SCHEMA: return False,"ENTRY_CONTEXT_SCHEMA_INVALID"
    digest=context.get("evidence_sha256")
    base={k:v for k,v in context.items() if k!="evidence_sha256"}
    try: valid_hash=_canonical_hash(base)==digest
    except (TypeError,ValueError): valid_hash=False
    if not valid_hash: return False,"ENTRY_CONTEXT_DIGEST_MISMATCH"
    gate_digest=context.get("gate_evidence_sha256")
    if not isinstance(gate_digest,str) or len(gate_digest)!=64 or any(c not in "0123456789abcdef" for c in gate_digest):
        return False,"ENTRY_CONTEXT_GATE_EVIDENCE_DIGEST_INVALID"
    if gate_evidence is not None and gate_digest!=_canonical_hash({k:v for k,v in gate_evidence.items() if k!="entry_context"}):
        return False,"ENTRY_CONTEXT_GATE_EVIDENCE_MISMATCH"
    if context.get("source")!="strategy_policy_v2" or context.get("market_data_source")!="gateio_public_spot" or context.get("symbol")!="BTC_USDT" or context.get("timeframe")!="15m":
        return False,"ENTRY_CONTEXT_SCOPE_INVALID"
    direction=context.get("direction")
    if direction not in ("LONG","SHORT") or (expected_direction is not None and direction!=expected_direction):
        return False,"ENTRY_CONTEXT_DIRECTION_MISMATCH"
    if context.get("setup_validated_15m") is not True or context.get("risk_gate_state")!="RISK_APPROVED":
        return False,"ENTRY_CONTEXT_UPSTREAM_GATE_NOT_PASSED"
    if context.get("execution_enabled") is not False or context.get("orders_placed") is not False:
        return False,"ENTRY_CONTEXT_EXECUTION_BOUNDARY_VIOLATION"
    observed=context.get("observed_at"); valid_until=context.get("valid_until")
    if isinstance(observed,bool) or not isinstance(observed,int) or isinstance(valid_until,bool) or not isinstance(valid_until,int):
        return False,"ENTRY_CONTEXT_TIME_INVALID"
    if isinstance(now_s,bool) or not isinstance(now_s,int) or now_s<observed or now_s>valid_until:
        return False,"ENTRY_CONTEXT_EXPIRED_OR_FUTURE"
    try:
        low=float(context["entry_zone_low"]); high=float(context["entry_zone_high"])
        entry=float(context["planned_entry_price"])
        stop=float(context["stop_price"]); target=float(context["target_price"])
        fraction=context.get("entry_zone_fraction_of_risk")
        if (context.get("entry_zone_policy")!=ENTRY_ZONE_POLICY
            or isinstance(fraction,bool) or not isinstance(fraction,(int,float))
            or not math.isclose(float(fraction),ENTRY_ZONE_FRACTION_OF_RISK,rel_tol=0,abs_tol=1e-12)):
            raise ValueError()
        if not all(math.isfinite(x) and x>0 for x in (low,high,entry,stop,target)) or low>high:
            raise ValueError()
        risk=abs(entry-stop); width=risk*ENTRY_ZONE_FRACTION_OF_RISK
        expected=(entry-width,entry) if direction=="LONG" else (entry,entry+width)
        if not math.isclose(low,expected[0],rel_tol=1e-10,abs_tol=1e-9) or not math.isclose(high,expected[1],rel_tol=1e-10,abs_tol=1e-9):
            raise ValueError()
        if direction=="LONG" and not stop<low<=entry==high<target: raise ValueError()
        if direction=="SHORT" and not target<low==entry<=high<stop: raise ValueError()
        if abs(target-entry)/abs(entry-stop)<3.0: raise ValueError()
    except (KeyError,TypeError,ValueError,ZeroDivisionError):
        return False,"ENTRY_CONTEXT_GEOMETRY_INVALID"
    return True,None
