#!/usr/bin/env python3
"""Independent forward-data validation for matured NO_TRADE decisions (24-48h old)."""
import hashlib, json, os, sys, re, math
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
CODE_ROOT=Path(__file__).resolve().parents[1]
DATA_ROOT=Path(os.environ.get('HES_DATA_ROOT', '/opt/hes-trade-agent')).expanduser().resolve()
DATA=DATA_ROOT/'data/forward'
# Code imports must resolve from this immutable release, never from the mutable data root.
if str(CODE_ROOT) not in sys.path: sys.path.insert(0, str(CODE_ROOT))
from forward.strategy_family_router_v1 import route_strategy_family
from forward.structure_only_no_trade_shadow_v1 import evaluate_structure_only_shadow
JOURNAL=DATA/'trade_journal_v2.jsonl'; CANDLES=DATA/'global_market_candles_v1.jsonl'; CANDLES_1M=DATA/'global_market_candles_1m_v1.jsonl'; NEUTRAL=DATA/'neutral_decision_outcomes_v1.jsonl'
REPORT=DATA/'matured_no_trade_validation_v1.json'; RECORDS=DATA/'matured_no_trade_validation_v1.jsonl'
HORIZONS={'1h':3600,'4h':14400,'24h':86400}
MIN_RR=3.0
RR_EPSILON=1e-9
def dt(v):
    x=v if isinstance(v,datetime) else datetime.fromisoformat(str(v).replace('Z','+00:00'))
    if x.tzinfo is None: x=x.replace(tzinfo=timezone.utc)
    return x.astimezone(timezone.utc)
def read(path):
    if not path.exists(): return []
    out=[]
    for i,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as e: raise ValueError(f'MALFORMED_JSONL:{path.name}:{i}') from e
        if not isinstance(row,dict): raise ValueError(f'INVALID_RECORD:{path.name}:{i}')
        out.append(row)
    return out
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def gate_qualification(decision, direction):
    """A proposal is a valid setup only when frozen confirmation, structure and risk gates passed."""
    gate = decision.get("gate_evidence")
    if not isinstance(gate, dict):
        return {"status": "UNKNOWN", "final_policy_pending": False,
                "confirmation_state": None, "risk_state": None, "structure_regime": None,
                "reasons": ["GATE_EVIDENCE_MISSING"]}
    confirmation = gate.get("confirmation") or {}
    risk = gate.get("risk") or {}
    structure = gate.get("structure") or {}
    raw_reasons = decision.get("gate_reasons") or decision.get("final_gate_reasons") or []
    if isinstance(raw_reasons, str):
        raw_reasons = [x for x in raw_reasons.split("|") if x]
    reasons = [str(x) for x in raw_reasons if x]
    confirmation_checks = confirmation.get("checks") or []
    risk_checks = risk.get("checks") or []
    checks_pass = (
        bool(confirmation_checks) and
        all(isinstance(x, dict) and x.get("state") == "PASS" for x in confirmation_checks) and
        bool(risk_checks) and
        all(isinstance(x, dict) and x.get("state") == "PASS" for x in risk_checks)
    )
    entry, stop, target = (decision.get("proposal_entry"), decision.get("proposal_stop_loss"), decision.get("proposal_take_profit"))
    geometry_status = "MISSING"
    geometry_valid = False
    rr = None
    if all(value is not None for value in (entry, stop, target)) and direction in ("LONG", "SHORT"):
        try:
            entry, stop, target = (float(value) for value in (entry, stop, target))
            finite_positive = all(math.isfinite(value) and value > 0 for value in (entry, stop, target))
            directional_order = (stop < entry < target if direction == "LONG" else target < entry < stop)
            risk_distance = abs(entry - stop)
            rr = abs(target - entry) / risk_distance if risk_distance > 0 else None
            geometry_valid = bool(finite_positive and directional_order and rr is not None and rr + RR_EPSILON >= MIN_RR)
            geometry_status = "VALID" if geometry_valid else "INVALID"
        except (TypeError, ValueError, OverflowError):
            geometry_status = "INVALID"
    if not geometry_valid:
        reasons.append("PROPOSAL_GEOMETRY_" + geometry_status)
    disqualifying_reasons = [x for x in reasons if x != "FINAL_POLICY_APPROVAL_REQUIRED"]
    qualified = (
        direction in ("LONG", "SHORT")
        and geometry_valid
        and confirmation.get("state") == f"CONFIRMED_{direction}"
        and risk.get("state") == "RISK_APPROVED"
        and structure.get("status") == "OBSERVED"
        and structure.get("regime") not in (None, "", "UNKNOWN")
        and checks_pass
        and not disqualifying_reasons
    )
    final_policy_pending = qualified and reasons == ["FINAL_POLICY_APPROVAL_REQUIRED"]
    return {
        "status": "QUALIFIED" if qualified else "REJECTED",
        "final_policy_pending": final_policy_pending,
        "geometry_status": geometry_status,
        "geometry_valid": geometry_valid,
        "rr": round(rr, 9) if rr is not None and math.isfinite(rr) else None,
        "confirmation_state": confirmation.get("state"),
        "risk_state": risk.get("state"),
        "structure_regime": structure.get("regime"),
        "reasons": reasons,
    }

def independent_candidate_attribution(decision, *, candidate_generation_authorized=None):
    """Keep independent structural candidate, proposal direction and risk geometry separate."""
    gate = decision.get("gate_evidence") or {}
    confirmation = gate.get("confirmation") or {}
    structure = gate.get("structure") or {}
    checks = confirmation.get("checks") or []
    by_name = {x.get("name"): x for x in checks if isinstance(x, dict)}
    align_ref = str((by_name.get("direction_regime_alignment") or {}).get("evidence_ref", ""))
    match = re.search(r"candidate_direction:(LONG|SHORT)", align_ref)
    candidate_direction = match.group(1) if match else None
    candidate_valid = (by_name.get("candidate_valid") or {}).get("state") == "PASS"
    structural_event = (by_name.get("structural_event_present") or {}).get("state") == "PASS"
    regime = structure.get("regime") or decision.get("market_regime") or "UNKNOWN"
    regime_aligned = ((regime == "UPTREND" and candidate_direction == "LONG")
        or (regime == "DOWNTREND" and candidate_direction == "SHORT")
        or (regime == "RANGE" and candidate_direction in ("LONG", "SHORT")))
    detected = bool(candidate_valid and structural_event and regime_aligned)
    proposal_direction = decision.get("proposal_direction") or "NONE"
    raw = [decision.get("proposal_entry"), decision.get("proposal_stop_loss"), decision.get("proposal_take_profit")]
    geometry_present = all(value is not None for value in raw)
    geometry_valid = False
    rr = None
    if detected and geometry_present:
        try:
            entry, stop, target = (float(value) for value in raw)
            finite_positive = all(math.isfinite(value) and value > 0 for value in (entry, stop, target))
            directional_order = (stop < entry < target if candidate_direction == "LONG" else target < entry < stop)
            risk = abs(entry - stop)
            rr = abs(target - entry) / risk if risk > 0 else None
            geometry_valid = bool(finite_positive and directional_order and rr is not None and rr + RR_EPSILON >= MIN_RR)
        except (TypeError, ValueError, OverflowError):
            geometry_valid = False
    direction_match = proposal_direction == candidate_direction
    if not detected:
        status = "NO_INDEPENDENT_CANDIDATE"
    elif not geometry_present and proposal_direction == "NONE":
        status = "STRUCTURE_ONLY_CANDIDATE_NO_PROPOSAL"
    elif not geometry_present:
        status = "PROPOSAL_GEOMETRY_MISSING"
    elif not geometry_valid:
        status = "CANDIDATE_GEOMETRY_INVALID"
    elif not direction_match:
        status = "CANDIDATE_PROPOSAL_DIRECTION_MISMATCH"
    else:
        status = "ALIGNED_COUNTERFACTUAL_CANDIDATE"
    return {
        "status": status, "independent_candidate_detected": detected,
        "candidate_direction": candidate_direction, "proposal_direction": proposal_direction,
        "regime": regime, "regime_direction_aligned": regime_aligned,
        "candidate_valid_pass": candidate_valid, "structural_event_pass": structural_event,
        "geometry_present": geometry_present, "geometry_valid": geometry_valid,
        "proposal_direction_matches_candidate": direction_match,
        "proposal_exists": proposal_direction in ("LONG", "SHORT"),
        "candidate_generation_authorized": candidate_generation_authorized,
        "rr": round(rr, 6) if rr is not None and math.isfinite(rr) else None,
        "confirmation_state": confirmation.get("state"),
        "risk_state": (gate.get("risk") or {}).get("state"),
    }

def rejection_attribution(decision, candidate_info=None):
    """Classify the primary NO_TRADE reason without guessing human emotion."""
    gate = decision.get("gate_evidence") or {}
    reasons = decision.get("gate_reasons") or decision.get("final_gate_reasons") or []
    if isinstance(reasons, str):
        reasons = [x for x in reasons.split("|") if x]
    reasons = [str(x) for x in reasons if x]
    reason_text = " ".join(reasons).upper()
    regime = ((gate.get("structure") or {}).get("regime")
              or decision.get("market_regime") or "UNKNOWN")
    risk_state = (gate.get("risk") or {}).get("state")
    confirmation_state = (gate.get("confirmation") or {}).get("state")
    if "FINAL_POLICY_APPROVAL_REQUIRED" in reasons:
        category = "POLICY_NOT_AUTHORIZED"
    elif any(x in reason_text for x in ("STALE", "GAP", "SCHEMA", "DATA_QUALITY", "CANDLE_INVALID", "SOURCE_UNAVAILABLE")):
        category = "DATA_QUALITY"
    elif regime in ("UNKNOWN", "TRANSITION_UNCERTAIN") or "MARKET_STRUCTURE_UNKNOWN" in reason_text:
        category = "REGIME_UNCERTAINTY"
    elif candidate_info and candidate_info.get("status") == "STRUCTURE_ONLY_CANDIDATE_NO_PROPOSAL" and candidate_info.get("candidate_generation_authorized") is False:
        category = "CANDIDATE_GENERATION_LOCKED"
    elif candidate_info and candidate_info.get("status") == "STRUCTURE_ONLY_CANDIDATE_NO_PROPOSAL":
        category = "STRUCTURE_ONLY_CANDIDATE_REVIEW"
    elif candidate_info and candidate_info.get("status") == "PROPOSAL_GEOMETRY_MISSING":
        category = "PROPOSAL_GEOMETRY_INCOMPLETE"
    elif candidate_info and candidate_info.get("status") == "CANDIDATE_GEOMETRY_INVALID":
        category = "INVALID_PROPOSAL_GEOMETRY"
    elif candidate_info and candidate_info.get("status") == "CANDIDATE_PROPOSAL_DIRECTION_MISMATCH":
        category = "PROPOSAL_DIRECTION_MISMATCH"
    elif confirmation_state not in (None, "CONFIRMED_LONG", "CONFIRMED_SHORT") or "CONFIRMATION_NOT_VALID" in reason_text:
        category = "CONFIRMATION_REJECT"
    elif any(x in reason_text for x in ("NO_VALID_CANDIDATE", "NO_CONFIRMED_20_BAR_BREAKOUT", "MOMENTUM_OR_FLOW_NOT_CONFIRMED", "PRICE_NOT_ALIGNED")):
        category = "NO_VALID_SETUP"
    elif risk_state == "RISK_REJECTED" or any(x in reason_text for x in ("RISK_REJECT", "RISK_GATE", "RISK_GEOMETRY")):
        category = "RISK_REJECT"
    else:
        category = "OTHER"
    return {"primary_category": category, "reason_codes": reasons,
            "independent_candidate_detected": bool(candidate_info and candidate_info.get("independent_candidate_detected")),
            "human_fear_inferred": False}

def build(now=None):
    now=dt(now or datetime.now(timezone.utc)); end=now-timedelta(hours=24); start=now-timedelta(hours=48)
    journal=read(JOURNAL); raw=read(CANDLES); neutral=read(NEUTRAL); raw_1m=read(CANDLES_1M)
    candles_1m=[]; invalid_1m=0
    for item in raw_1m:
        try:
            int(item["open_time"])
            candles_1m.append(item)
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid_1m+=1
    candles_1m.sort(key=lambda x:int(x["open_time"]))
    one_minute_times=[int(x["open_time"]) for x in candles_1m]
    duplicate_1m=sum(1 for a,b in zip(one_minute_times,one_minute_times[1:]) if b==a)
    gaps_1m=sum(1 for a,b in zip(one_minute_times,one_minute_times[1:]) if b-a!=60)
    candles=[]; invalid=0
    for c in raw:
        if c.get('source')!='gateio_public_spot' or c.get('symbol')!='BTC_USDT' or c.get('timeframe')!='15m' or c.get('closed') is not True: continue
        try:
            ct=int(c['close_time']); op=int(c['open_time']); o,h,l,cl=[float(c[k]) for k in ('open','high','low','close')]
            if ct-op!=900 or min(o,h,l,cl)<=0 or l>min(o,cl) or h<max(o,cl): raise ValueError('BAD_OHLC')
            candles.append((ct,c))
        except (KeyError,ValueError,TypeError,OverflowError): invalid+=1
    candles.sort(key=lambda x:x[0])
    # Fail closed on duplicate close times or gaps in any evaluated interval.
    ts_by_event={}; bad_ts=0
    for r in journal:
        if r.get('decision')!='NO_TRADE' or not r.get('event_id'): continue
        try: t=dt(r['observed_at'])
        except (KeyError,ValueError,TypeError,OverflowError): bad_ts+=1; continue
        if start <= t < end:
            if r['event_id'] not in ts_by_event or t>ts_by_event[r['event_id']][0]: ts_by_event[r['event_id']]=(t,r)
    neutral_by={}
    for r in neutral:
        eid=r.get('decision_event_id'); h=r.get('horizon')
        if eid and h in HORIZONS and r.get('horizon_complete') is True: neutral_by.setdefault((str(eid),h),r)
    recs=[]; counts=Counter(); complete_24h=0; comparisons=0; mismatches=0
    for eid,(t,decision) in sorted(ts_by_event.items(),key=lambda kv:(kv[1][0],kv[0])):
        prior=[c for ct,c in candles if ct<=t.timestamp()]
        baseline=float(prior[-1]['close']) if prior else None
        hs={}
        for h,seconds in HORIZONS.items():
            cutoff=t.timestamp()+seconds
            # Match the outcome tracker: include the first closed candle at or after
            # the exact horizon boundary. A close just before the boundary is not enough.
            selected_pairs=[]
            for ct,c in candles:
                if ct<=t.timestamp():
                    continue
                selected_pairs.append((ct,c))
                if ct>=cutoff:
                    break
            selected=[c for _,c in selected_pairs]
            close_times=[int(ct) for ct,_ in selected_pairs]
            baseline_close_time=int(prior[-1]['close_time']) if prior else None
            expected=((close_times[-1]-baseline_close_time)//900) if close_times and baseline_close_time is not None else 0
            contiguous=(bool(close_times) and baseline_close_time is not None
                and close_times[0]==baseline_close_time+900
                and close_times[-1]>=cutoff and close_times[-1]<cutoff+900
                and len(close_times)==expected
                and all(b-a==900 for a,b in zip(close_times,close_times[1:])))
            metric={'expected_candles':expected,'observed_candles':len(selected),'gap_free_complete':bool(contiguous),'baseline_available':baseline is not None}
            if contiguous and baseline and baseline>0:
                last=float(selected[-1]['close']); high=max(float(c['high']) for c in selected); low=min(float(c['low']) for c in selected)
                metric.update({'last_close':last,'close_change_pct':round((last/baseline-1)*100,6),'max_high_excursion_pct':round((high/baseline-1)*100,6),'max_low_excursion_pct':round((low/baseline-1)*100,6)})
            else: metric['status']='INCOMPLETE_OR_GAPPED'
            tracker=neutral_by.get((str(eid),h)); metric['tracker_record_available']=tracker is not None
            # Tracker samples the first closed candle at/after the horizon boundary; cross-check separately.
            boundary=[c for ct,c in candles if ct>t.timestamp() and ct>=cutoff]
            if tracker and boundary and tracker.get('baseline_close') is not None and tracker.get('last_close') is not None:
                b=float(tracker['baseline_close']); lc=float(boundary[0]['close'])
                calc=round((lc/b-1)*100,6) if b>0 else None
                matches=(abs(float(tracker['last_close'])-lc)<1e-7 and calc is not None and abs(float(tracker.get('close_change_pct',999))-calc)<0.000002)
                metric['tracker_boundary_crosscheck']='PASS' if matches else 'MISMATCH'
                comparisons+=1
                if not matches: mismatches+=1
            else: metric['tracker_boundary_crosscheck']='NOT_COMPARABLE'
            hs[h]=metric
        if hs['24h']['gap_free_complete'] and baseline: complete_24h+=1
        statuses=[('COMPLETE' if m['gap_free_complete'] else 'INCOMPLETE') for m in hs.values()]
        status='VALIDATED_24H' if hs['24h']['gap_free_complete'] and baseline else 'INCOMPLETE_FORWARD_COVERAGE'
        counts[status]+=1
        structure_snapshot=(decision.get('gate_evidence') or {}).get('structure',{})
        regime=structure_snapshot.get('regime') or decision.get('market_regime') or 'UNKNOWN'
        route=route_strategy_family(source=decision.get('evidence_source') or decision.get('source') or 'gateio_public_spot',symbol=decision.get('symbol') or 'BTC_USDT',timeframe=decision.get('timeframe') or '15m',regime=regime).as_dict()
        candidate_attribution=independent_candidate_attribution(decision, candidate_generation_authorized=route.get("candidate_generation_authorized"))
        rejection= rejection_attribution(decision,candidate_attribution)
        shadow_result=evaluate_structure_only_shadow(decision,candles_1m)
        recs.append({'schema':'hes_matured_no_trade_validation_record_v1','event_id':str(eid),'observed_at':t.isoformat(),'decision':'NO_TRADE','direction':decision.get('direction') or 'NONE','proposal_direction':decision.get('proposal_direction') or 'NONE','gate_reasons':decision.get('gate_reasons') or decision.get('final_gate_reasons') or [],'gate_qualification':gate_qualification(decision,decision.get('proposal_direction') or decision.get('direction') or 'NONE'),'independent_candidate_attribution':candidate_attribution,'rejection_attribution':rejection,'structure_only_shadow':shadow_result,'structure_regime':regime,'strategy_family_route':route,'strategy_family_id':route.get('family_id'),'strategy_family_version':route.get('family_version'),'strategy_family_activation_state':route.get('activation_state'),'horizons':hs,'validation_status':status,'interpretation':'Market movement is observational. Family attribution is regime-based metadata only; it does not establish a valid setup or authorize trading. Only a frozen proposal that passed confirmation, structure and risk gates can be treated as a qualified directional setup; gate-rejected proposals are reported separately.','policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False})
    # Counterfactual outcomes are joined back to the immutable decision-time gate snapshot.
    # A price move after a rejected proposal is NOT a missed profitable trade.
    cohort_ids={str(x['event_id']) for x in recs}
    decision_by_event={str(eid):row for eid,(_,row) in ts_by_event.items()}
    counterfactual_groups={
        "qualified": {h:Counter() for h in HORIZONS},
        "preapproval": {h:Counter() for h in HORIZONS},
        "rejected": {h:Counter() for h in HORIZONS},
        "unverified": {h:Counter() for h in HORIZONS},
    }
    group_decisions={k:set() for k in counterfactual_groups}
    group_loss={k:set() for k in counterfactual_groups}
    group_win={k:set() for k in counterfactual_groups}
    for r in neutral:
        eid=str(r.get("decision_event_id") or "")
        h=r.get("horizon"); cls=r.get("outcome_class")
        if eid not in cohort_ids or h not in HORIZONS or r.get("horizon_complete") is not True:
            continue
        direction=r.get("directional_proposal")
        geometry=(direction in ("LONG","SHORT") and
                  all(r.get(k) is not None for k in ("entry","stop_loss","take_profit")))
        if not geometry:
            continue
        qualification=gate_qualification(decision_by_event.get(eid,{}),direction)
        if qualification["status"]=="QUALIFIED" and qualification["final_policy_pending"]:
            group="preapproval"
        elif qualification["status"]=="QUALIFIED":
            group="qualified"
        elif qualification["status"]=="REJECTED":
            group="rejected"
        else:
            group="unverified"
        counterfactual_groups[group][h][cls or "UNKNOWN"] += 1
        group_decisions[group].add(eid)
        if cls in ("STOP_LOSS","TIMEOUT_NEGATIVE"):
            group_loss[group].add(eid)
        if cls in ("TAKE_PROFIT","TIMEOUT_POSITIVE"):
            group_win[group].add(eid)

    def summarize_counterfactual_group(group, interpretation):
        return {
            "evaluated_unique_decisions":len(group_decisions[group]),
            "decisions_with_any_negative_hypothetical_outcome":len(group_loss[group]),
            "decisions_with_any_positive_hypothetical_outcome":len(group_win[group]),
            "outcome_class_counts_by_horizon":{h:dict(c) for h,c in counterfactual_groups[group].items()},
            "interpretation":interpretation,
        }
    directional_counterfactuals=summarize_counterfactual_group(
        "qualified","Only proposals whose frozen confirmation, observed structure and risk gates passed; still counterfactual, not proof of executable fills or causality.")
    preapproval_hold_counterfactuals=summarize_counterfactual_group(
        "preapproval","All operational gates passed but final policy approval remained pending; reported separately and never counted as an authorized trade.")
    rejected_proposal_counterfactuals=summarize_counterfactual_group(
        "rejected","Proposal geometry existed but one or more decision-time gates rejected it; subsequent TP/SL is diagnostic context, not a missed trade or avoided loss.")
    unverified_proposal_counterfactuals=summarize_counterfactual_group(
        "unverified","Proposal geometry existed but the frozen gate evidence was missing; not eligible for performance attribution.")

    # One outcome per decision/horizon; prefer the row carrying complete proposal geometry.
    outcomes_by_decision_horizon={}
    for r in neutral:
        eid=str(r.get("decision_event_id") or ""); h=r.get("horizon")
        if not eid or h not in HORIZONS or r.get("horizon_complete") is not True: continue
        key=(eid,h)
        prior=outcomes_by_decision_horizon.get(key)
        if prior is None or (r.get("directional_proposal") in ("LONG","SHORT") and all(r.get(k) is not None for k in ("entry","stop_loss","take_profit"))):
            outcomes_by_decision_horizon[key]=r
    bucket_template={
        "matured_decisions":0,"valid_directional_setup":0,
        "avoided_loss_hypotheses":0,"missed_profit_hypotheses":0,
        "preapproval_hold_directional_setup":0,
        "preapproval_hold_avoided_loss_hypotheses":0,
        "preapproval_hold_missed_profit_hypotheses":0,
        "gate_rejected_proposals":0,
        "rejected_proposal_avoided_loss_hypotheses":0,
        "rejected_proposal_missed_profit_hypotheses":0,
        "unverified_proposals":0,
        "ambiguous_barrier_cases":0,"flat_or_zero_move":0,
        "unclassifiable_no_valid_setup":0,"large_move_context_only":0,
    }
    decision_quality={h:dict(bucket_template) for h in HORIZONS}
    for (eid,h),r in outcomes_by_decision_horizon.items():
        if eid not in cohort_ids: continue
        b=decision_quality[h]; b["matured_decisions"]+=1
        cls=r.get("outcome_class")
        direction=r.get("directional_proposal")
        geometry=(direction in ("LONG","SHORT") and
                  all(r.get(k) is not None for k in ("entry","stop_loss","take_profit")))
        if not geometry:
            b["unclassifiable_no_valid_setup"]+=1
            if abs(float(r.get("close_change_pct") or 0))>=0.5 or abs(float(r.get("max_favorable_excursion_pct") or 0))>=0.5 or abs(float(r.get("max_adverse_excursion_pct") or 0))>=0.5:
                b["large_move_context_only"]+=1
            continue
        qualification=gate_qualification(decision_by_event.get(eid,{}),direction)
        if qualification["status"]=="UNKNOWN":
            b["unverified_proposals"]+=1
            continue
        if qualification["status"]=="REJECTED":
            b["gate_rejected_proposals"]+=1
            if cls in ("STOP_LOSS","TIMEOUT_NEGATIVE"): b["rejected_proposal_avoided_loss_hypotheses"]+=1
            elif cls in ("TAKE_PROFIT","TIMEOUT_POSITIVE"): b["rejected_proposal_missed_profit_hypotheses"]+=1
            elif cls=="AMBIGUOUS_SAME_CANDLE": b["ambiguous_barrier_cases"]+=1
            else: b["flat_or_zero_move"]+=1
            continue
        if qualification["final_policy_pending"]:
            b["preapproval_hold_directional_setup"]+=1
            if cls in ("STOP_LOSS","TIMEOUT_NEGATIVE"): b["preapproval_hold_avoided_loss_hypotheses"]+=1
            elif cls in ("TAKE_PROFIT","TIMEOUT_POSITIVE"): b["preapproval_hold_missed_profit_hypotheses"]+=1
            elif cls=="AMBIGUOUS_SAME_CANDLE": b["ambiguous_barrier_cases"]+=1
            else: b["flat_or_zero_move"]+=1
            continue
        b["valid_directional_setup"]+=1
        if cls in ("STOP_LOSS","TIMEOUT_NEGATIVE"): b["avoided_loss_hypotheses"]+=1
        elif cls in ("TAKE_PROFIT","TIMEOUT_POSITIVE"): b["missed_profit_hypotheses"]+=1
        elif cls=="AMBIGUOUS_SAME_CANDLE": b["ambiguous_barrier_cases"]+=1
        else: b["flat_or_zero_move"]+=1
    family_summary=defaultdict(lambda:{'decisions':0,'complete_gap_free_24h':0,'validation_status_counts':Counter(),'gate_qualification_counts':Counter(),'gate_reason_counts':Counter(),'regimes':Counter()})
    for record in recs:
        family=record.get('strategy_family_id') or 'UNROUTED'
        bucket=family_summary[family]; bucket['decisions']+=1
        if record['horizons']['24h']['gap_free_complete']: bucket['complete_gap_free_24h']+=1
        bucket['validation_status_counts'][record['validation_status']]+=1
        bucket['gate_qualification_counts'][record['gate_qualification']['status']]+=1
        for reason in record.get('gate_reasons') or []: bucket['gate_reason_counts'][str(reason)]+=1
        bucket['regimes'][record['structure_regime']]+=1
    family_summary_json={family:{'decisions':v['decisions'],'complete_gap_free_24h':v['complete_gap_free_24h'],'validation_status_counts':dict(v['validation_status_counts']),'gate_qualification_counts':dict(v['gate_qualification_counts']),'gate_reason_counts':dict(v['gate_reason_counts']),'regime_counts':dict(v['regimes']),'activation_state':next((x['strategy_family_activation_state'] for x in recs if x.get('strategy_family_id')==family),None),'interpretation':'Regime-based cohort attribution only; not strategy performance or authorization.'} for family,v in family_summary.items()}
    independent_status_counts=Counter(x['independent_candidate_attribution']['status'] for x in recs)
    independent_by_family_regime_direction=defaultdict(Counter)
    for x in recs:
        a=x['independent_candidate_attribution']
        key='|'.join((x.get('strategy_family_id') or 'UNKNOWN',a.get('regime') or 'UNKNOWN',a.get('candidate_direction') or 'NONE'))
        independent_by_family_regime_direction[key][a['status']]+=1
    independent_candidate_summary={
        'decision_count':len(recs),
        'independent_candidate_count':sum(x['independent_candidate_attribution']['independent_candidate_detected'] for x in recs),
        'status_counts':dict(independent_status_counts),
        'by_family_regime_direction':{k:dict(v) for k,v in independent_by_family_regime_direction.items()},
        'interpretation':'Independent structure candidates are recorded separately from the strategy proposal. Missing/invalid geometry or direction mismatch is NOT counted as missed profit or avoided loss. Only ALIGNED_COUNTERFACTUAL_CANDIDATE records may enter the counterfactual ledger.',
    }
    rejection_category_counts=Counter(x['rejection_attribution']['primary_category'] for x in recs)
    rejection_by_family_regime=defaultdict(Counter)
    for x in recs:
        key='|'.join((x.get('strategy_family_id') or 'UNKNOWN',x.get('structure_regime') or 'UNKNOWN'))
        rejection_by_family_regime[key][x['rejection_attribution']['primary_category']]+=1
    rejection_attribution_summary={
        'primary_category_counts':dict(rejection_category_counts),
        'by_family_and_regime':{k:dict(v) for k,v in rejection_by_family_regime.items()},
        'human_fear_inferred':False,
        'interpretation':'Structure-only candidates, locked candidate generation, incomplete/invalid proposal geometry and gate rejections are separated. None is treated as an actual missed trade; human fear is never inferred from NO_TRADE or price movement alone.',
    }
    shadow_status_counts=Counter(x['structure_only_shadow']['status'] for x in recs)
    shadow_by_direction=defaultdict(Counter)
    shadow_net_sensitivity=defaultdict(lambda:defaultdict(lambda:{'net_positive':0,'net_nonpositive':0,'complete':0}))
    for x in recs:
        shadow=x['structure_only_shadow']; direction=shadow.get('direction') or 'NONE'
        for horizon,outcome in (shadow.get('horizons') or {}).items():
            shadow_by_direction[f'{direction}|{horizon}'][outcome.get('outcome_class','UNKNOWN')]+=1
            for bps,metric in (outcome.get('net_sensitivity_long_only') or {}).items():
                bucket=shadow_net_sensitivity[horizon][bps]
                bucket['complete']+=1
                bucket['net_positive' if metric.get('net_positive') else 'net_nonpositive']+=1
    shadow_target_reviews=defaultdict(list)
    for record in recs:
        shadow=record['structure_only_shadow']
        if shadow.get('status')!='SHADOW_EVALUATED':
            continue
        direction=shadow.get('direction') or 'NONE'
        entry_time=shadow.get('entry_time')
        stop=shadow.get('stop_loss')
        cluster_id=(f"{direction}|{float(stop):.8f}|{int(entry_time)//14400}"
                    if stop is not None and entry_time is not None else f"{direction}|{record['event_id']}")
        for horizon,outcome in (shadow.get('horizons') or {}).items():
            if outcome.get('outcome_class')=='SHADOW_TARGET_HIT':
                shadow_target_reviews[horizon].append({
                    'event_id':record['event_id'],'observed_at':record.get('observed_at'),
                    'entry_time':entry_time,'direction':direction,
                    'strategy_family_id':record.get('strategy_family_id'),
                    'structure_regime':record.get('structure_regime'),
                    'gate_reasons':record.get('gate_reasons') or [],
                    'entry_price':shadow.get('entry_price'),'stop_loss':stop,
                    'take_profit':shadow.get('take_profit'),
                    'gross_return_pct':outcome.get('gross_return_pct'),
                    'gross_r':outcome.get('gross_r'),
                    'net_sensitivity_long_only':outcome.get('net_sensitivity_long_only') or {},
                    'review_cluster_id':cluster_id,
                })
    target_24h=shadow_target_reviews.get('24h',[])
    target_clusters=defaultdict(list)
    for event in target_24h:
        target_clusters[event['review_cluster_id']].append(event)
    target_cluster_representatives=[]
    for cluster_id,events in target_clusters.items():
        representative=min(events,key=lambda x:x.get('entry_time') or 0)
        target_cluster_representatives.append({
            'review_cluster_id':cluster_id,
            'event_count':len(events),
            'representative_event_id':representative['event_id'],
            'direction':representative['direction'],
            'strategy_family_id':representative.get('strategy_family_id'),
            'structure_regime':representative.get('structure_regime'),
            'entry_price':representative['entry_price'],
            'stop_loss':representative['stop_loss'],
            'take_profit':representative['take_profit'],
            'gross_return_pct':representative['gross_return_pct'],
            'net_sensitivity_long_only':representative['net_sensitivity_long_only'],
            'gate_reasons':representative['gate_reasons'],
        })
    shadow_summary={
        'protocol':'HES_STRUCTURE_ONLY_NO_TRADE_SHADOW_V1',
        'potential_missed_opportunity_review':{
            'status':'POTENTIAL_OVERFILTERED_CANDIDATE_REVIEW_ONLY',
            'target_hit_event_count_24h':len(target_24h),
            'unique_target_hit_cluster_count_24h':len(target_clusters),
            'cluster_representatives':target_cluster_representatives,
            'actual_missed_profit_claim':False,
            'interpretation':'Review candidates only. Full strategy confirmation did not pass; these are not counted as actual missed trades or realized profit.',
        },
        'status_counts':dict(shadow_status_counts),
        'evaluated_candidates':shadow_status_counts.get('SHADOW_EVALUATED',0),
        'outcomes_by_direction_and_horizon':{k:dict(v) for k,v in shadow_by_direction.items()},
        'long_net_sensitivity_counts_by_horizon':{h:{bps:dict(v) for bps,v in costs.items()} for h,costs in shadow_net_sensitivity.items()},
        'target_hit_review_events_by_horizon':{h:list(v) for h,v in shadow_target_reviews.items()},
        'target_hit_review_clusters_by_horizon':{h:len({x['review_cluster_id'] for x in v}) for h,v in shadow_target_reviews.items()},
        'review_cluster_rule':'Same direction + same decision-time swing stop + same 4h entry-time bucket; descriptive de-duplication only, not a strategy rule.',
        'feed_integrity':{'rows':len(candles_1m),'invalid_open_time_records':invalid_1m,'duplicate_open_times':duplicate_1m,'gaps':gaps_1m,'sha256':sha(CANDLES_1M)},
        'short_economics':'NOT_TESTABLE_FROM_SPOT',
        'interpretation':'Structure-only shadow outcomes are diagnostic candidate paths, not MISSED_PROFIT or AVOIDED_LOSS. Candidate events can overlap; target-hit review events are grouped by shared swing-stop cluster. No portfolio PF, compounded return or win-rate is computed.',
    }
    report={'schema':'hes_matured_no_trade_validation_v1','generated_at':now.isoformat(),'cohort_start_inclusive':start.isoformat(),'cohort_end_exclusive':end.isoformat(),'cohort_age_hours':'24_to_48','source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','decisions_in_matured_cohort':len(recs),'strategy_family_attribution':family_summary_json,'independent_candidate_attribution':independent_candidate_summary,'rejection_attribution':rejection_attribution_summary,'structure_only_shadow':shadow_summary,'validation_status_counts':dict(counts),'complete_gap_free_24h_decisions':complete_24h,'decision_quality_buckets_by_horizon':decision_quality,'decision_quality_methodology':{'valid_directional_setup':'Requires frozen LONG/SHORT direction and valid entry/SL/TP geometry plus CONFIRMED_LONG/CONFIRMED_SHORT, observed non-UNKNOWN structure, RISK_APPROVED and all recorded confirmation/risk checks PASS.','avoided_loss_hypothesis':'Only a qualified directional setup with STOP_LOSS or negative timeout; hypothetical, not causal proof.','missed_profit_hypothesis':'Only a qualified directional setup with TAKE_PROFIT or positive timeout; hypothetical, not proof of executable profit.','preapproval_hold':'All operational gates passed but FINAL_POLICY_APPROVAL_REQUIRED remained; shown separately, never treated as authorized execution.','gate_rejected_proposal':'Proposal geometry existed but confirmation/structure/risk gate(s) failed; its later outcome is diagnostic only, not a missed trade or avoided loss.','unverified_proposal':'Proposal geometry existed but decision-time gate evidence was absent.','unclassifiable':'No valid directional proposal and risk geometry were recorded at decision time. Directionless price movement is context only.','large_move_context_only_threshold_pct':0.5,'cost_model':'UNCONFIGURED; all classifications are gross hypothetical outcomes, not net profitability.'},'directional_counterfactuals':directional_counterfactuals,'preapproval_hold_counterfactuals':preapproval_hold_counterfactuals,'rejected_proposal_counterfactuals':rejected_proposal_counterfactuals,'unverified_proposal_counterfactuals':unverified_proposal_counterfactuals,'tracker_boundary_comparisons':comparisons,'tracker_boundary_mismatches':mismatches,'invalid_candles_excluded':invalid,'invalid_decision_timestamps_excluded':bad_ts,'horizon_quality_counts':{h:{'complete':sum(x['horizons'][h]['gap_free_complete'] for x in recs),'incomplete':sum(not x['horizons'][h]['gap_free_complete'] for x in recs)} for h in HORIZONS},'source_sha256':{'journal':sha(JOURNAL),'candles':sha(CANDLES),'neutral_outcomes':sha(NEUTRAL),'candles_1m':sha(CANDLES_1M)},'limitations':['Cohort validation requires 24-48h-old decisions and complete closed-candle coverage','Directionless market context is not directional strategy P&L','Counterfactual results do not prove causality and do not include verified fees/slippage','Cost model is not configured; no net profitability claim','No automatic policy mutation or execution'],'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False}
    # Write both files atomically only after all source parsing and evaluation succeeds.
    for path,content in ((RECORDS,''.join(json.dumps(x,sort_keys=True)+'\n' for x in recs)),(REPORT,json.dumps(report,indent=2,sort_keys=True)+'\n')):
        tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(content,encoding='utf-8'); tmp.replace(path)
    return report
if __name__=='__main__': print(json.dumps(build(),indent=2,sort_keys=True))
