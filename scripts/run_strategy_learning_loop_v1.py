#!/usr/bin/env python3
"""Read-only evidence-driven learning loop. Proposes hypotheses; never edits policy or executes orders."""
import json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
import sys
CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
ROOT=DATA_ROOT; DATA=ROOT/'data/forward'
sys.path.insert(0, str(CODE_ROOT/'scripts'))
from forward.neutral_decision_outcomes_v1 import run as update_neutral_outcomes
from run_decision_report_24h_v1 import build_report as update_decision_report
from run_no_trade_decision_audit_v1 import build_audit as update_no_trade_audit
from run_matured_no_trade_validation_v1 import build as update_matured_no_trade_validation
JOURNAL=DATA/'trade_journal_v2.jsonl'; OUTCOMES=DATA/'strategy_policy_v2_eval_outcomes.jsonl'; CANDIDATES=DATA/'strategy_policy_v2_eval_candidates.jsonl'; NEUTRAL_OUTCOMES=DATA/'neutral_decision_outcomes_v1.jsonl'
REPORT=DATA/'strategy_learning_v1_report.json'; HYPOTHESES=DATA/'strategy_learning_v1_hypotheses.jsonl'; STATE=DATA/'strategy_learning_v1_state.json'
def read_jsonl(p):
 rows=[]
 if p.exists():
  for n,line in enumerate(p.read_text().splitlines(),1):
   if line.strip():
    try: rows.append(json.loads(line))
    except json.JSONDecodeError as e: raise RuntimeError(f'malformed evidence {p.name}:{n}') from e
 return rows
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def read_acceptance():
 p=DATA/'strategy_policy_v2_eval_report.json'
 try:
  value=json.loads(p.read_text()).get('signal_quality_acceptance',{})
  return value if isinstance(value,dict) else {}
 except (OSError,json.JSONDecodeError): return {}
def candidate_event_id(row):
    return str(row.get('candidate_event_id') or row.get('event_id') or
               (f"hes-v2-candidate-{row.get('symbol','BTC_USDT')}-15m-{row.get('candidate_time')}"
                if row.get('candidate_time') is not None else ""))

def link_outcomes_to_candidates(outcomes, candidates):
    """Prefer stable IDs; legacy candidate_time fallback is accepted only when unique."""
    by_id={candidate_event_id(c):c for c in candidates if candidate_event_id(c)}
    by_time={}
    for c in candidates:
        if c.get('candidate_time') is not None:
            by_time.setdefault(str(c.get('candidate_time')),[]).append(c)
    linked=[]; unmatched=0; ambiguous=0
    for outcome in outcomes:
        cid=str(outcome.get('candidate_event_id') or "")
        candidate=by_id.get(cid) if cid else None
        if candidate is None and not cid and outcome.get('candidate_time') is not None:
            options=by_time.get(str(outcome.get('candidate_time')),[])
            if len(options)==1: candidate=options[0]
            elif len(options)>1: ambiguous+=1
        if candidate is None: unmatched+=1
        else: linked.append((outcome,candidate))
    return linked,unmatched,ambiguous

def classify_outcomes_by_gate(outcomes, candidates):
    """Only outcomes linked to candidates that passed operational gates count as strategy performance."""
    linked,_,_=link_outcomes_to_candidates(outcomes,candidates)
    eligible=[]; research_only=[]
    linked_row_ids=set()
    for row,candidate in linked:
        linked_row_ids.add(id(row))
        if candidate.get('final_gate_decision') in ('LONG','SHORT'): eligible.append(row)
        else: research_only.append(row)
    # Unmatched or ambiguous outcomes are research-only; they can never inflate performance.
    research_only.extend(row for row in outcomes if id(row) not in linked_row_ids)
    return eligible,research_only

def win_rate_target_met(*, resolved, win_rate_pct, unmatched_outcomes, ambiguous_outcomes, unscorable_outcomes, minimum_resolved, target_pct):
    return bool(resolved >= minimum_resolved and win_rate_pct is not None and win_rate_pct >= target_pct
                and unmatched_outcomes == 0 and ambiguous_outcomes == 0 and unscorable_outcomes == 0)

def main():
 while True:
  try:
   try:
    neutral_tracker_status=update_neutral_outcomes(ROOT)
   except Exception as tracker_error:
    neutral_tracker_status={'status':'ERROR_FAIL_CLOSED','error':type(tracker_error).__name__+':'+str(tracker_error)[:160]}
   try:
    decision_report_24h_status=update_decision_report()
   except Exception as report_error:
    decision_report_24h_status={'status':'ERROR_FAIL_CLOSED','error':type(report_error).__name__+':'+str(report_error)[:160]}
   try:
    no_trade_audit_status=update_no_trade_audit()
   except Exception as audit_error:
    no_trade_audit_status={'status':'ERROR_FAIL_CLOSED','error':type(audit_error).__name__+':'+str(audit_error)[:160]}
   try:
    integrated_validation=(decision_report_24h_status.get('matured_no_trade_validation')
      if isinstance(decision_report_24h_status,dict) else None)
    if isinstance(integrated_validation,dict) and integrated_validation.get('status')=='OK':
     matured_no_trade_validation_status=integrated_validation
    else:
     # Fail-safe fallback if the integrated 24h report could not refresh validation.
     matured_no_trade_validation_status=update_matured_no_trade_validation()
   except Exception as validation_error:
    matured_no_trade_validation_status={'status':'ERROR_FAIL_CLOSED','error':type(validation_error).__name__+':'+str(validation_error)[:160]}
   decisions=read_jsonl(JOURNAL); outcomes=read_jsonl(OUTCOMES); candidates=read_jsonl(CANDIDATES); neutral_outcomes=read_jsonl(NEUTRAL_OUTCOMES)
   counts={}; rejected={}
   for r in decisions:
    d=r.get('decision','UNKNOWN'); counts[d]=counts.get(d,0)+1
    for reason in r.get('gate_reasons',[]) or []: rejected[reason]=rejected.get(reason,0)+1
   eligible_outcomes,research_only_outcomes=classify_outcomes_by_gate(outcomes,candidates)
   linked_outcomes,unmatched_outcomes,ambiguous_outcomes=link_outcomes_to_candidates(outcomes,candidates)
   preapproval_ids={id(row) for row,candidate in linked_outcomes if candidate.get('final_gate_decision') not in ('LONG','SHORT') and candidate.get('preapproval_paper_eligible') is True}
   preapproval_outcomes=[row for row,candidate in linked_outcomes if id(row) in preapproval_ids]
   research_only_outcomes=[row for row in research_only_outcomes if id(row) not in preapproval_ids]
   cost_cfg={}
   try: cost_cfg=json.loads((ROOT/'forward/paper_risk_context_v1.json').read_text())
   except Exception: cost_cfg={}
   cost_side=float(cost_cfg.get('fee_fraction_per_side',0) or 0)+float(cost_cfg.get('slippage_fraction_per_side',0) or 0)
   def economic_counts(rows):
    wins=losses=flats=timeouts=unscorable=0
    for r in rows:
     outcome=str(r.get('outcome','')).lower()
     if outcome not in ('wins','losses','timeouts'): continue
     if outcome=='timeouts': timeouts+=1
     try:
      entry=float(r['entry']); direction=str(r['direction'])
      exit_price=float(r.get('exit_price') if r.get('exit_price') is not None else r.get('exit_close'))
      stop=float(r['stop_loss'])
      if entry<=0 or exit_price<=0 or stop<=0 or direction not in ('LONG','SHORT'): raise ValueError()
      reason=str(r.get('reason') or r.get('outcome_reason') or '')
      if outcome=='losses' and ('STOP_LOSS' in reason or 'STOP_AND_TARGET' in reason): exit_price=stop
      if outcome=='wins' and 'TAKE_PROFIT' in reason: exit_price=float(r.get('take_profit') or exit_price)
      gross=(exit_price-entry) if direction=='LONG' else (entry-exit_price)
      net=gross-(entry+exit_price)*cost_side
     except (KeyError,TypeError,ValueError):
      unscorable+=1
      continue
     if net>0: wins+=1
     elif net<0: losses+=1
     else: flats+=1
    resolved=wins+losses+flats
    return {'wins':wins,'losses':losses,'flats':flats,'timeouts':timeouts,'resolved':resolved,
            'win_rate_pct':round(100*wins/resolved,2) if resolved else None,'unscorable':unscorable}
   ec=economic_counts(eligible_outcomes); pc=economic_counts(preapproval_outcomes); rc=economic_counts(research_only_outcomes)
   wins=ec['wins']; losses=ec['losses']; flats=ec['flats']; timeouts=ec['timeouts']
   resolved=ec['resolved']; wr=ec['win_rate_pct']
   research_wins=rc['wins']; research_losses=rc['losses']; research_timeouts=rc['timeouts']
   outcome_by_direction={}
   for row in eligible_outcomes:
    direction=row.get('direction','UNKNOWN')
    bucket=outcome_by_direction.setdefault(direction,{'wins':0,'losses':0,'timeouts':0,'resolved':0,'win_rate_pct':None})
    result=row.get('outcome')
    if result in ('wins','losses','timeouts'): bucket[result]+=1
   for bucket in outcome_by_direction.values():
    bucket['resolved']=bucket['wins']+bucket['losses']
    bucket['win_rate_pct']=round(100*bucket['wins']/bucket['resolved'],2) if bucket['resolved'] else None
   linked_outcomes,unmatched_outcomes,ambiguous_outcomes=link_outcomes_to_candidates(outcomes,candidates)
   candidate_ids={candidate_event_id(row) for row in candidates if candidate_event_id(row)}
   linked_candidate_ids={candidate_event_id(candidate) for _,candidate in linked_outcomes if candidate_event_id(candidate)}
   matched_outcomes=len(linked_outcomes)
   unresolved_candidates=len(candidate_ids-linked_candidate_ids)
   hypotheses=[]
   for reason,n in sorted(rejected.items(),key=lambda x:(-x[1],x[0]))[:10]:
    hypotheses.append({'hypothesis_id':'gate-'+hashlib.sha256(reason.encode()).hexdigest()[:10],'type':'GATE_ATTRIBUTION_REVIEW','gate_reason':reason,'observations':n,'proposal':'Inspect feature availability and rejection calibration; do not relax the gate without a preregistered out-of-sample test.','status':'HYPOTHESIS_ONLY'})
   acceptance=read_acceptance()
   precision_resolved=int(acceptance.get('resolved_closed_trade_count',0) or 0)
   if acceptance.get('status')!='PASS': hypotheses.append({'hypothesis_id':'precision-entry-acceptance-monitor-v1','type':'PRECISION_ENTRY_ACCEPTANCE_MONITOR','resolved_trades':precision_resolved,'proposal':'Continue forward-only 1m precision-entry paper collection. Official acceptance requires strictly >90% win rate over at least 100 resolved closed 1m READY candidates, no more than 3 actionable entries per UTC day, verified fee/slippage provenance, clean candidate/outcome linkage, and independent out-of-sample evidence. 15m preapproval and research-only outcomes are baseline diagnostics and do not count.','status':'HYPOTHESIS_ONLY'})
   if not candidates: hypotheses.append({'hypothesis_id':'candidate-flow-check','type':'CANDIDATE_FLOW_DIAGNOSTIC','proposal':'Check whether locked policy conditions generate candidates across observed regimes; never fabricate trades or bypass risk gates.','status':'HYPOTHESIS_ONLY'})
   neutral_complete=[r for r in neutral_outcomes if r.get('horizon_complete') is True]
   neutral_classes={}
   for row in neutral_complete:
    cls=row.get('outcome_class','UNKNOWN'); neutral_classes[cls]=neutral_classes.get(cls,0)+1
   if neutral_complete:
    hypotheses.append({'hypothesis_id':'neutral-decision-outcome-review-v1','type':'NO_TRADE_COUNTERFACTUAL_REVIEW','observations':len(neutral_complete),'outcome_classes':neutral_classes,'proposal':'Compare NO_TRADE gate reasons with forward-only outcomes; separate avoided losses, plausible missed opportunities, directionless context and ambiguous candles. No policy change without independent out-of-sample evidence.','status':'HYPOTHESIS_ONLY'})
   old=read_jsonl(HYPOTHESES); ids={x.get('hypothesis_id') for x in old}; new=[h for h in hypotheses if h['hypothesis_id'] not in ids]
   with HYPOTHESES.open('a') as f:
    for h in new: f.write(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),**h},sort_keys=True)+'\n')
    f.flush()
   report={'schema':'hes_strategy_learning_loop_v1','updated_at':datetime.now(timezone.utc).isoformat(),'mode':'READ_ONLY_HYPOTHESIS_ONLY','policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False,'decision_records':len(decisions),'decision_counts':counts,'gate_rejection_counts':rejected,'candidate_records':len(candidates),'neutral_tracker_status':neutral_tracker_status,'decision_report_24h_status':({'generated_at':decision_report_24h_status.get('generated_at'),'decision_counts':decision_report_24h_status.get('decision_counts'),'no_trade_decisions_in_window':decision_report_24h_status.get('no_trade_decisions_in_window')} if 'schema' in decision_report_24h_status else decision_report_24h_status),'no_trade_decision_audit_status':({'generated_at':no_trade_audit_status.get('generated_at'),'unique_no_trade_decisions':no_trade_audit_status.get('unique_no_trade_decisions'),'screen_status_counts':no_trade_audit_status.get('screen_status_counts')} if 'schema' in no_trade_audit_status else no_trade_audit_status),'matured_no_trade_validation_status':({'generated_at':matured_no_trade_validation_status.get('generated_at'),'decisions_in_matured_cohort':matured_no_trade_validation_status.get('decisions_in_matured_cohort'),'complete_gap_free_24h_decisions':matured_no_trade_validation_status.get('complete_gap_free_24h_decisions'),'directional_counterfactuals':matured_no_trade_validation_status.get('directional_counterfactuals'),'preapproval_hold_counterfactuals':matured_no_trade_validation_status.get('preapproval_hold_counterfactuals'),'rejected_proposal_counterfactuals':matured_no_trade_validation_status.get('rejected_proposal_counterfactuals'),'unverified_proposal_counterfactuals':matured_no_trade_validation_status.get('unverified_proposal_counterfactuals'),'decision_quality_buckets_by_horizon':matured_no_trade_validation_status.get('decision_quality_buckets_by_horizon'),'decision_quality_methodology':matured_no_trade_validation_status.get('decision_quality_methodology'),'validation_status_counts':matured_no_trade_validation_status.get('validation_status_counts'),'horizon_quality_counts':matured_no_trade_validation_status.get('horizon_quality_counts'),'tracker_boundary_mismatches':matured_no_trade_validation_status.get('tracker_boundary_mismatches')} if 'schema' in matured_no_trade_validation_status else matured_no_trade_validation_status),'neutral_decision_outcome_records':len(neutral_outcomes),'neutral_decision_outcome_complete_records':len(neutral_complete),'neutral_decision_outcome_class_counts':neutral_classes,'neutral_outcome_evidence_sha256':sha(NEUTRAL_OUTCOMES),'resolved_outcomes':resolved,'wins':wins,'losses':losses,'flats':flats,'timeouts':timeouts,'unscorable_eligible_outcomes':ec['unscorable'],'preapproval_paper_outcomes':len(preapproval_outcomes),'preapproval_paper_resolved':pc['resolved'],'preapproval_paper_wins':pc['wins'],'preapproval_paper_losses':pc['losses'],'preapproval_paper_flats':pc['flats'],'preapproval_paper_timeouts':pc['timeouts'],'preapproval_paper_win_rate_pct':pc['win_rate_pct'],'preapproval_paper_unscorable_outcomes':pc['unscorable'],'precision_entry_paper_target_met':acceptance.get('status')=='PASS','win_rate_pct':wr,'decisive_win_rate_pct':round(100*wins/(wins+losses),2) if wins+losses else None,'cost_model':{'status':'ASSUMPTION_BASED' if cost_side>0 else 'UNAVAILABLE','fee_fraction_per_side':float(cost_cfg.get('fee_fraction_per_side',0) or 0),'slippage_fraction_per_side':float(cost_cfg.get('slippage_fraction_per_side',0) or 0),'note':'Simulation assumptions only; not verified exchange/account costs.'},'performance_scope':'GATE_APPROVED_ONLY','research_only_outcomes':len(research_only_outcomes),'research_only_wins':research_wins,'research_only_losses':research_losses,'research_only_timeouts':research_timeouts,'excluded_rejected_outcomes':len(research_only_outcomes),'outcomes_by_direction':outcome_by_direction,'candidate_outcome_match_count':matched_outcomes,'unmatched_outcome_count':unmatched_outcomes,'ambiguous_legacy_outcome_match_count':ambiguous_outcomes,'preapproval_paper_candidate_count':sum(r.get('preapproval_paper_eligible') is True for r in candidates),'gate_approved_candidate_count':sum(r.get('final_gate_decision') in ('LONG','SHORT') for r in candidates),'gate_rejected_candidate_count':sum(r.get('final_gate_decision') not in ('LONG','SHORT') for r in candidates),'unresolved_candidate_count':unresolved_candidates,'target_win_rate_pct':acceptance.get('target_win_rate_pct'),'minimum_resolved_trades_for_claim':acceptance.get('minimum_resolved_closed_trades'),'target_met':acceptance.get('status')=='PASS','target_policy_status':acceptance.get('status','NOT_MET'),'paper_performance_scope':acceptance.get('performance_cohort','PRECISION_ENTRY_PAPER_ELIGIBLE'),'signal_quality_acceptance':acceptance,'precision_entry_resolved_closed_trades':precision_resolved,'precision_entry_win_rate_pct':acceptance.get('observed_win_rate_pct'),'evidence_sha256':{'journal':sha(JOURNAL),'outcomes':sha(OUTCOMES),'candidates':sha(CANDIDATES)},'new_hypotheses_added':len(new),'hypotheses_total':len(old)+len(new),'limitations':['NO_TRADE counterfactual outcomes are observational and do not prove causality','Directionless NO_TRADE records are market-context only, not invented trades','Raw neutral outcome class counts include gate-rejected proposal counterfactuals and directionless context; use gate-qualified matured buckets for attribution.','Net outcome estimates use explicit unverified simulation fee/slippage assumptions, not verified exchange/account costs','No automatic threshold tuning','No policy changes','No live orders','Gate counts are not causal attribution','Official target requires strictly >90% over at least 100 resolved 1m precision-entry paper trades; 15m preapproval and research-only cohorts are excluded','Cost-adjusted expectancy requires reliable fill and cost model','Stable candidate IDs are preferred; legacy timestamp fallback is accepted only when unique','Cost-adjusted results use explicit unverified simulation fee/slippage assumptions and are not live performance']}
   REPORT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); STATE.write_text(json.dumps({'last_updated':report['updated_at'],'last_evidence':report['evidence_sha256']},indent=2)+'\n')
   print(json.dumps({'updated_at':report['updated_at'],'decisions':len(decisions),'candidates':len(candidates),'resolved':resolved,'win_rate_pct':wr,'new_hypotheses':len(new),'target_met':report['target_met'],'policy_mutation_enabled':False}),flush=True)
  except Exception as e: print(json.dumps({'error':type(e).__name__+':'+str(e)[:200],'policy_mutation_enabled':False,'execution_enabled':False}),flush=True)
  time.sleep(300)
if __name__=='__main__': main()
