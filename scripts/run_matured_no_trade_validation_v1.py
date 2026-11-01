#!/usr/bin/env python3
"""Independent forward-data validation for matured NO_TRADE decisions (24-48h old)."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
ROOT=DATA_ROOT; DATA=ROOT/'data/forward'
JOURNAL=DATA/'trade_journal_v2.jsonl'; CANDLES=DATA/'global_market_candles_v1.jsonl'; NEUTRAL=DATA/'neutral_decision_outcomes_v1.jsonl'
REPORT=DATA/'matured_no_trade_validation_v1.json'; RECORDS=DATA/'matured_no_trade_validation_v1.jsonl'
HORIZONS={'1h':3600,'4h':14400,'24h':86400}
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
    disqualifying_reasons = [x for x in reasons if x != "FINAL_POLICY_APPROVAL_REQUIRED"]
    qualified = (
        direction in ("LONG", "SHORT")
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
        "confirmation_state": confirmation.get("state"),
        "risk_state": risk.get("state"),
        "structure_regime": structure.get("regime"),
        "reasons": reasons,
    }
def build(now=None):
    now=dt(now or datetime.now(timezone.utc)); end=now-timedelta(hours=24); start=now-timedelta(hours=48)
    journal=read(JOURNAL); raw=read(CANDLES); neutral=read(NEUTRAL)
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
        recs.append({'schema':'hes_matured_no_trade_validation_record_v1','event_id':str(eid),'observed_at':t.isoformat(),'decision':'NO_TRADE','direction':decision.get('direction') or 'NONE','proposal_direction':decision.get('proposal_direction') or 'NONE','gate_reasons':decision.get('gate_reasons') or decision.get('final_gate_reasons') or [],'gate_qualification':gate_qualification(decision,decision.get('proposal_direction') or decision.get('direction') or 'NONE'),'structure_regime':(decision.get('gate_evidence') or {}).get('structure',{}).get('regime','UNKNOWN'),'horizons':hs,'validation_status':status,'interpretation':'Market movement is observational. Only a frozen proposal that passed confirmation, structure and risk gates can be treated as a qualified directional setup; gate-rejected proposals are reported separately.','policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False})
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
    report={'schema':'hes_matured_no_trade_validation_v1','generated_at':now.isoformat(),'cohort_start_inclusive':start.isoformat(),'cohort_end_exclusive':end.isoformat(),'cohort_age_hours':'24_to_48','source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','decisions_in_matured_cohort':len(recs),'validation_status_counts':dict(counts),'complete_gap_free_24h_decisions':complete_24h,'decision_quality_buckets_by_horizon':decision_quality,'decision_quality_methodology':{'valid_directional_setup':'Requires frozen LONG/SHORT direction and valid entry/SL/TP geometry plus CONFIRMED_LONG/CONFIRMED_SHORT, observed non-UNKNOWN structure, RISK_APPROVED and all recorded confirmation/risk checks PASS.','avoided_loss_hypothesis':'Only a qualified directional setup with STOP_LOSS or negative timeout; hypothetical, not causal proof.','missed_profit_hypothesis':'Only a qualified directional setup with TAKE_PROFIT or positive timeout; hypothetical, not proof of executable profit.','preapproval_hold':'All operational gates passed but FINAL_POLICY_APPROVAL_REQUIRED remained; shown separately, never treated as authorized execution.','gate_rejected_proposal':'Proposal geometry existed but confirmation/structure/risk gate(s) failed; its later outcome is diagnostic only, not a missed trade or avoided loss.','unverified_proposal':'Proposal geometry existed but decision-time gate evidence was absent.','unclassifiable':'No valid directional proposal and risk geometry were recorded at decision time. Directionless price movement is context only.','large_move_context_only_threshold_pct':0.5,'cost_model':'UNCONFIGURED; all classifications are gross hypothetical outcomes, not net profitability.'},'directional_counterfactuals':directional_counterfactuals,'preapproval_hold_counterfactuals':preapproval_hold_counterfactuals,'rejected_proposal_counterfactuals':rejected_proposal_counterfactuals,'unverified_proposal_counterfactuals':unverified_proposal_counterfactuals,'tracker_boundary_comparisons':comparisons,'tracker_boundary_mismatches':mismatches,'invalid_candles_excluded':invalid,'invalid_decision_timestamps_excluded':bad_ts,'horizon_quality_counts':{h:{'complete':sum(x['horizons'][h]['gap_free_complete'] for x in recs),'incomplete':sum(not x['horizons'][h]['gap_free_complete'] for x in recs)} for h in HORIZONS},'source_sha256':{'journal':sha(JOURNAL),'candles':sha(CANDLES),'neutral_outcomes':sha(NEUTRAL)},'limitations':['Cohort validation requires 24-48h-old decisions and complete closed-candle coverage','Directionless market context is not directional strategy P&L','Counterfactual results do not prove causality and do not include verified fees/slippage','Cost model is not configured; no net profitability claim','No automatic policy mutation or execution'],'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False}
    # Write both files atomically only after all source parsing and evaluation succeeds.
    for path,content in ((RECORDS,''.join(json.dumps(x,sort_keys=True)+'\n' for x in recs)),(REPORT,json.dumps(report,indent=2,sort_keys=True)+'\n')):
        tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(content,encoding='utf-8'); tmp.replace(path)
    return report
if __name__=='__main__': print(json.dumps(build(),indent=2,sort_keys=True))
