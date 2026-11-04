#!/usr/bin/env python3
"""Forward-only paper evaluator. No live orders."""
import json,sys,time
from pathlib import Path
from datetime import datetime,timezone
CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
ROOT=DATA_ROOT
from forward.global_market_data_reader_v1 import load_market_input, build_market_data_batch_provenance
from scripts.analyze_gateio_snapshot_v1 import snapshot
from forward.strategy_policy_v2 import evaluate,POLICY_VERSION
from forward.strategy_policy_gate_v1 import enforce_final_gates
from forward.strategy_gate_pipeline_v1 import evaluate_gate_evidence
from forward.forward_journal_v1 import ForwardJournalV1
from forward.signal_quality_acceptance_v1 import evaluate_acceptance
from forward.strategy_entry_context_v1 import build_entry_context
BASE=ROOT/'data/forward'; STATE=BASE/'strategy_policy_v2_eval_state.json'
CAND=BASE/'strategy_policy_v2_eval_candidates.jsonl'; OUT=BASE/'strategy_policy_v2_eval_outcomes.jsonl'; REPORT=BASE/'strategy_policy_v2_eval_report.json'
MAX_SECONDS=86400
JOURNAL=ForwardJournalV1(BASE/'trade_journal_v2.jsonl')
def append(p,x):
 # All JSONL artifacts, including candidates and outcomes, use the same
 # per-file lock, strict existing-history validation and event-id idempotency.
 if not ForwardJournalV1(p).append_event(x):
  return False
 return True
def sync_outcomes_to_journal():
 # Idempotently reconcile candidate and outcome ledgers into the human-auditable trade journal.
 journal=BASE/'trade_journal_v2.jsonl'
 known=set()
 if journal.exists():
  for line in journal.read_text().splitlines():
   try:
    row=json.loads(line)
    if row.get('event_id'): known.add(row['event_id'])
   except json.JSONDecodeError: raise RuntimeError('malformed trade journal; refusing to append')
 for path,kind in ((CAND,'PAPER_CANDIDATE'),(OUT,'PAPER_OUTCOME')):
  if not path.exists(): continue
  for line in path.read_text().splitlines():
   if not line.strip(): continue
   row=json.loads(line)
   if kind=='PAPER_CANDIDATE':
    event_id=f"hes-v2-candidate-{row.get('symbol','BTC_USDT')}-15m-{row['candidate_time']}"
    event={'schema':'hes_trade_journal_paper_candidate_v1','event_id':event_id,'candidate_event_id':event_id,'observed_at':row.get('observed_at'),'candle_close_time':row.get('candidate_time'),'symbol':row.get('symbol','BTC_USDT'),'timeframe':'15m','direction':row.get('direction'),'decision':kind,'entry':row.get('entry'),'stop_loss':row.get('stop_loss'),'take_profit':row.get('take_profit'),'rr':row.get('rr'),'final_gate_decision':row.get('final_gate_decision'),'final_gate_reasons':row.get('final_gate_reasons',[]),'outcome':None,'execution_enabled':False,'orders_placed':False}
   else:
    event_id=row.get('event_id') or f"hes-v2-outcome-BTC_USDT-15m-{row.get('candidate_time')}"
    event={'schema':'hes_trade_journal_paper_outcome_v1','event_id':event_id,'candidate_event_id':row.get('candidate_event_id'),'observed_at':row.get('resolved_at'),'candidate_time':row.get('candidate_time'),'symbol':'BTC_USDT','timeframe':'15m','direction':row.get('direction'),'decision':kind,'entry':row.get('entry'),'stop_loss':row.get('stop_loss'),'take_profit':row.get('take_profit'),'outcome':row.get('outcome'),'exit_time':row.get('exit_close_time'),'exit_close':row.get('exit_close'),'exit_price':row.get('exit_price'),'outcome_reason':row.get('reason'),'policy_version':row.get('policy_version',POLICY_VERSION),'execution_enabled':False,'orders_placed':False}
   if event_id not in known:
    append(journal,event); known.add(event_id)
def _candidate_event_id(row):
 # Stable identity is preferred; legacy rows get a deterministic identity from their candle.
 return str(row.get('candidate_event_id') or row.get('event_id') or
            (f"hes-v2-candidate-{row.get('symbol','BTC_USDT')}-15m-{row.get('candidate_time')}"
             if row.get('candidate_time') is not None else ""))

def preapproval_paper_eligibility(proposal, gate_evidence):
 # Research-only paper cohort: all observable structure/confirmation/risk checks must pass,
 # while the final policy-approval gate remains closed. This never authorizes live execution.
 reasons=[]
 direction=getattr(proposal,'direction','NONE')
 if getattr(proposal,'decision','NO_TRADE') not in ('LONG','SHORT') or direction not in ('LONG','SHORT'):
  reasons.append('NO_DIRECTIONAL_POLICY_PROPOSAL')
 structure=gate_evidence.get('structure',{}) if isinstance(gate_evidence,dict) else {}
 confirmation=gate_evidence.get('confirmation',{}) if isinstance(gate_evidence,dict) else {}
 risk=gate_evidence.get('risk',{}) if isinstance(gate_evidence,dict) else {}
 if structure.get('status')!='OBSERVED' or structure.get('regime')=='UNKNOWN':
  reasons.append('STRUCTURE_EVIDENCE_NOT_VALID')
 if confirmation.get('state') != ('CONFIRMED_'+direction if direction in ('LONG','SHORT') else 'NO_VALID_DIRECTION'):
  reasons.append('CONFIRMATION_NOT_VALID')
 if risk.get('state')!='RISK_APPROVED':
  reasons.append('RISK_NOT_APPROVED')
 try:
  entry=float(proposal.entry); stop=float(proposal.stop_loss); target=float(proposal.take_profit); rr=float(proposal.rr)
  geometry=(entry>0 and stop>0 and target>0 and rr>=3.0 and
            ((stop<entry<target) if direction=='LONG' else (target<entry<stop) if direction=='SHORT' else False))
 except (TypeError,ValueError):
  geometry=False
 if not geometry: reasons.append('RISK_GEOMETRY_INVALID')
 if not isinstance(gate_evidence,dict) or gate_evidence.get('execution_enabled') is not False or gate_evidence.get('orders_placed') is not False:
  reasons.append('PAPER_SAFETY_INVARIANT_NOT_CONFIRMED')
 return {'eligible':not reasons,'status':'PREAPPROVAL_PAPER_ELIGIBLE' if not reasons else 'BLOCKED',
         'reasons':reasons,'final_gate_approval_required':True,
         'execution_enabled':False,'orders_placed':False}

def win_rate_target_met(metrics, *, minimum_resolved=100, target_pct=90.0, cohort='eligible'):
 # Contract uses strict >90%; exactly 90% never passes.
 prefix='preapproval_paper' if cohort=='preapproval_paper' else 'eligible'
 return bool(
  int(metrics.get(prefix+'_resolved', 0)) >= minimum_resolved
  and metrics.get(prefix+'_win_rate_pct') is not None
  and float(metrics[prefix+'_win_rate_pct']) > target_pct
  and int(metrics.get('unmatched_outcome_records', 0)) == 0
  and int(metrics.get('ambiguous_legacy_timestamp_matches', 0)) == 0
  and int(metrics.get(prefix+'_unscorable_outcomes', 0)) == 0
 )

def performance_metrics():
 # Only proposals that actually passed every operational gate count as strategy trades.
 # Prefer stable candidate IDs. Legacy timestamp matching is allowed only when unique.
 candidates=[]
 if CAND.exists():
  candidates=[json.loads(line) for line in CAND.read_text().splitlines() if line.strip()]
 by_id={_candidate_event_id(row):row for row in candidates if _candidate_event_id(row)}
 by_time={}
 for row in candidates:
  if row.get('candidate_time') is not None:
   by_time.setdefault(str(row.get('candidate_time')),[]).append(row)
 outcomes=[json.loads(line) for line in OUT.read_text().splitlines() if line.strip()] if OUT.exists() else []
 linked=[]; unmatched=0; ambiguous=0
 for row in outcomes:
  cid=str(row.get('candidate_event_id') or "")
  candidate=by_id.get(cid) if cid else None
  if candidate is None and not cid and row.get('candidate_time') is not None:
   possible=by_time.get(str(row.get('candidate_time')),[])
   if len(possible)==1: candidate=possible[0]
   elif len(possible)>1: ambiguous+=1
  if candidate is None:
   unmatched+=1
   continue
  linked.append((row,candidate))
 approved=[(r,c) for r,c in linked if c.get('final_gate_decision') in ('LONG','SHORT')]
 preapproval=[(r,c) for r,c in linked if c.get('final_gate_decision') not in ('LONG','SHORT') and c.get('preapproval_paper_eligible') is True]
 research=[(r,c) for r,c in linked if c.get('final_gate_decision') not in ('LONG','SHORT') and c.get('preapproval_paper_eligible') is not True]
 fee=slip=0.0
 try:
  cfg=json.loads((ROOT/'forward/paper_risk_context_v1.json').read_text())
  fee=float(cfg['fee_fraction_per_side']); slip=float(cfg['slippage_fraction_per_side'])
 except (OSError,ValueError,KeyError,TypeError):
  fee=slip=0.0
 cost_side=fee+slip
 def score(rows):
  wins=losses=flats=timeouts=unscorable=0; net_r_values=[]; net_pnl_values=[]
  for r,c in rows:
   outcome=str(r.get('outcome','')).lower()
   if outcome not in ('wins','losses','timeouts'): continue
   if outcome=='timeouts': timeouts+=1
   direction=str(r.get('direction') or c.get('direction') or '')
   entry=r.get('entry',c.get('entry')); stop=r.get('stop_loss',c.get('stop_loss'))
   target=r.get('take_profit',c.get('take_profit'))
   exit_price=r.get('exit_price')
   if exit_price is None:
    reason=str(r.get('reason') or '')
    if 'STOP_LOSS' in reason or 'STOP_AND_TARGET' in reason: exit_price=stop
    elif 'TAKE_PROFIT' in reason: exit_price=target
    else: exit_price=r.get('exit_close')
   try:
    entry=float(entry); stop=float(stop); exit_price=float(exit_price)
    if entry<=0 or stop<=0 or exit_price<=0 or direction not in ('LONG','SHORT'): raise ValueError()
   except (TypeError,ValueError):
    unscorable+=1
    continue
   gross=(exit_price-entry) if direction=='LONG' else (entry-exit_price)
   net=gross-(entry+exit_price)*cost_side
   risk=abs(entry-stop)
   net_r=net/risk if risk>0 else None
   net_pnl_values.append(net)
   if net_r is not None: net_r_values.append(net_r)
   if net>0: wins+=1
   elif net<0: losses+=1
   else: flats+=1
  resolved=wins+losses+flats
  return {'wins':wins,'losses':losses,'timeouts':timeouts,'flats':flats,
          'resolved':resolved,'win_rate_pct':round(100*wins/resolved,2) if resolved else None,
          'decisive_win_rate_pct':round(100*wins/(wins+losses),2) if wins+losses else None,
          'net_R_sum_assumption_based':round(sum(net_r_values),6) if net_r_values else None,
          'net_pnl_per_unit_sum_assumption_based':round(sum(net_pnl_values),6) if net_pnl_values else None,
          'unscorable_outcomes':unscorable}
 e=score(approved); pp=score(preapproval); r=score(research)
 return {'eligible_wins':e['wins'],'eligible_losses':e['losses'],'eligible_timeouts':e['timeouts'],
         'eligible_flats':e['flats'],'eligible_resolved':e['resolved'],
         'eligible_win_rate_pct':e['win_rate_pct'],'eligible_decisive_win_rate_pct':e['decisive_win_rate_pct'],
         'eligible_net_R_sum_assumption_based':e['net_R_sum_assumption_based'],
         'eligible_net_pnl_per_unit_sum_assumption_based':e['net_pnl_per_unit_sum_assumption_based'],
         'eligible_unscorable_outcomes':e['unscorable_outcomes'],
         'preapproval_paper_outcomes':len(preapproval),'preapproval_paper_wins':pp['wins'],
         'preapproval_paper_losses':pp['losses'],'preapproval_paper_timeouts':pp['timeouts'],
         'preapproval_paper_flats':pp['flats'],'preapproval_paper_resolved':pp['resolved'],
         'preapproval_paper_win_rate_pct':pp['win_rate_pct'],
         'preapproval_paper_decisive_win_rate_pct':pp['decisive_win_rate_pct'],
         'preapproval_paper_net_R_sum_assumption_based':pp['net_R_sum_assumption_based'],
         'preapproval_paper_unscorable_outcomes':pp['unscorable_outcomes'],
         'research_only_wins':r['wins'],'research_only_losses':r['losses'],
         'research_only_timeouts':r['timeouts'],'research_only_flats':r['flats'],
         'research_only_resolved':r['resolved'],'research_only_win_rate_pct':r['win_rate_pct'],
         'research_only_net_R_sum_assumption_based':r['net_R_sum_assumption_based'],
         'excluded_rejected_outcomes':len(research),'outcome_records':len(outcomes),
         'candidate_records':len(candidates),'preapproval_paper_candidate_records':sum(c.get('preapproval_paper_eligible') is True for c in candidates),'linked_outcome_records':len(linked),
         'unmatched_outcome_records':unmatched,'ambiguous_legacy_timestamp_matches':ambiguous,
         'cost_model':{'status':'ASSUMPTION_BASED' if cost_side>0 else 'UNAVAILABLE',
                       'fee_fraction_per_side':fee,'slippage_fraction_per_side':slip,
                       'cost_fraction_per_side':cost_side,
                       'note':'Simulation assumptions only; not verified exchange/account costs.'}}

def main():
 try: st=json.loads(STATE.read_text())
 except Exception: st={'last_seen':None,'active':[],'wins':0,'losses':0,'timeouts':0,'ambiguous_losses':0}
 print('EVALUATOR_STARTED '+POLICY_VERSION,flush=True)
 while True:
  try:
   src=load_market_input(root=ROOT);frames=src['timeframes'];bars=frames['15m'];now=int(bars[-1]['close_time'])
   sync_outcomes_to_journal()
   pending=[]
   for t in st['active']:
    done=False
    for b in bars:
     ct=int(b['close_time'])
     if ct<=t['candidate_time']:continue
     hi=float(b['high']);lo=float(b['low']);islong=t['direction']=='LONG'
     sl=lo<=t['stop_loss'] if islong else hi>=t['stop_loss']
     tp=hi>=t['take_profit'] if islong else lo<=t['take_profit']
     if sl or tp:
      outcome='losses' if sl else 'wins'; reason='STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS' if sl and tp else 'STOP_LOSS' if sl else 'TAKE_PROFIT'
      st[outcome]+=1
      if sl and tp:st['ambiguous_losses']+=1
      closed_at=datetime.now(timezone.utc).isoformat()
      candidate_event_id=t.get('candidate_event_id') or f"hes-v2-candidate-{src['symbol'] if 'src' in locals() else 'BTC_USDT'}-15m-{t['candidate_time']}"
      exit_price=float(t['stop_loss']) if sl else float(t['take_profit'])
      outcome_record={'schema':'hes_strategy_policy_v2_paper_outcome','event_id':f"hes-v2-outcome-{src['symbol'] if 'src' in locals() else 'BTC_USDT'}-15m-{t['candidate_time']}",'candidate_event_id':candidate_event_id,'preapproval_paper_eligible':bool(t.get('preapproval_paper_eligible',False)),'policy_version':POLICY_VERSION,'candidate_time':t['candidate_time'],'direction':t['direction'],'final_gate_decision':t.get('final_gate_decision','UNKNOWN'),'performance_eligible':t.get('final_gate_decision') in ('LONG','SHORT'),'entry':t['entry'],'stop_loss':t['stop_loss'],'take_profit':t['take_profit'],'outcome':outcome,'exit_close_time':ct,'exit_close':float(b['close']),'exit_price':exit_price,'reason':reason,'resolved_at':closed_at,'execution_enabled':False,'orders_placed':False}
      append(OUT,outcome_record)
      append(BASE/'trade_journal_v2.jsonl',{'schema':'hes_trade_journal_paper_outcome_v1','event_id':outcome_record['event_id'],'observed_at':closed_at,'symbol':'BTC_USDT','timeframe':'15m','direction':t['direction'],'decision':'PAPER_OUTCOME','candidate_time':t['candidate_time'],'candidate_event_id':candidate_event_id,'entry':t['entry'],'stop_loss':t['stop_loss'],'take_profit':t['take_profit'],'outcome':outcome,'exit_time':ct,'exit_close':float(b['close']),'outcome_reason':reason,'policy_version':POLICY_VERSION,'execution_enabled':False,'orders_placed':False})
      done=True;break
     if ct-t['candidate_time']>=MAX_SECONDS:
      st['timeouts']+=1
      closed_at=datetime.now(timezone.utc).isoformat()
      candidate_event_id=t.get('candidate_event_id') or f"hes-v2-candidate-{src['symbol']}-15m-{t['candidate_time']}"
      outcome_record={'schema':'hes_strategy_policy_v2_paper_outcome','event_id':f"hes-v2-timeout-{t['candidate_time']}",'candidate_event_id':candidate_event_id,'preapproval_paper_eligible':bool(t.get('preapproval_paper_eligible',False)),'policy_version':POLICY_VERSION,'candidate_time':t['candidate_time'],'direction':t['direction'],'final_gate_decision':t.get('final_gate_decision','UNKNOWN'),'performance_eligible':t.get('final_gate_decision') in ('LONG','SHORT'),'outcome':'timeouts','exit_close_time':ct,'exit_close':float(b['close']),'exit_price':float(b['close']),'reason':'MAX_HOLD_24H','resolved_at':closed_at,'execution_enabled':False,'orders_placed':False}
      append(OUT,outcome_record)
      append(BASE/'trade_journal_v2.jsonl',{'schema':'hes_trade_journal_paper_outcome_v1','event_id':outcome_record['event_id'],'observed_at':closed_at,'symbol':'BTC_USDT','timeframe':'15m','direction':t['direction'],'decision':'PAPER_OUTCOME','candidate_time':t['candidate_time'],'candidate_event_id':candidate_event_id,'entry':t['entry'],'stop_loss':t['stop_loss'],'take_profit':t['take_profit'],'outcome':'timeouts','exit_time':ct,'exit_price':float(b['close']),'exit_close':float(b['close']),'outcome_reason':'MAX_HOLD_24H','policy_version':POLICY_VERSION,'execution_enabled':False,'orders_placed':False})
      done=True;break
    if not done:pending.append(t)
   st['active']=pending
   gate_evidence=None
   if REPORT.exists():
    try: gate_evidence=json.loads(REPORT.read_text()).get('latest_gate_evidence')
    except Exception: gate_evidence=None
   new_candle = now != st.get('last_seen')
   feats={tf:snapshot(tf,rows) for tf,rows in frames.items()};proposal=evaluate(feats)
   gate_evidence=evaluate_gate_evidence(proposal=proposal,rows_15m=frames['15m'],frames=frames,source=src['source'],symbol=src['symbol'],observed_at=now)
   market_data_provenance=build_market_data_batch_provenance(src)
   gate_evidence['market_data_provenance']=market_data_provenance
   d=enforce_final_gates(proposal,gate_evidence)
   preapproval={'eligible':False,'status':'BLOCKED','reasons':['NO_DIRECTIONAL_15M_PROPOSAL'],'final_gate_approval_required':True,'execution_enabled':False,'orders_placed':False}
   entry_context=None
   if proposal.decision in ('LONG','SHORT') and proposal.entry is not None:
    preapproval=preapproval_paper_eligibility(proposal,gate_evidence)
    if preapproval['eligible']:
     try:
      entry_context=build_entry_context(source=src['source'],symbol=src['symbol'],candidate_time=now,policy_version=POLICY_VERSION,direction=proposal.direction,entry=proposal.entry,stop=proposal.stop_loss,target=proposal.take_profit,gate_evidence=gate_evidence)
      gate_evidence['entry_context']=entry_context
     except (TypeError,ValueError) as context_error:
      preapproval={'eligible':False,'status':'BLOCKED','reasons':['ENTRY_CONTEXT_BUILD_FAILED:'+str(context_error)[:120]],'final_gate_approval_required':True,'execution_enabled':False,'orders_placed':False}
   if new_candle:
    # Append every closed-candle decision to the validated immutable trade journal.
    # A proposal is not an approved trade: operational gate decision is what is journaled.
    record={
     'event_id':f"hes-v2-{src['symbol']}-15m-{now}",
     'observed_at':datetime.now(timezone.utc).isoformat(),
     'symbol':src['symbol'],'timeframe':'15m','market_regime':gate_evidence['structure']['regime'],
     'direction':d.decision if d.decision in ('LONG','SHORT') else 'NONE',
     'signal_state':proposal.decision,'confirmation_state':gate_evidence['confirmation']['state'],'risk_state':gate_evidence['risk']['state'],
     'decision':d.decision,'entry':proposal.entry if d.decision in ('LONG','SHORT') else None,
     'stop_loss':proposal.stop_loss if d.decision in ('LONG','SHORT') else None,
     'take_profit':proposal.take_profit if d.decision in ('LONG','SHORT') else None,
     'rr':proposal.rr if d.decision in ('LONG','SHORT') else None,
     'quality_score':proposal.quality_score,
     'no_trade_reason':'|'.join(d.reasons) if d.decision=='NO_TRADE' else None,
     'outcome':None,'closed_at':None,'evidence_source':src['source'],
     'policy_version':POLICY_VERSION,'proposal_decision':proposal.decision,
     'proposal_direction':proposal.direction,'proposal_entry':proposal.entry,
     'proposal_stop_loss':proposal.stop_loss,'proposal_take_profit':proposal.take_profit,
     'proposal_rr':proposal.rr,'proposal_reasons':list(proposal.reasons),
     'gate_reasons':list(d.reasons),'gate_evidence':gate_evidence,'market_structure_state':gate_evidence['structure']['regime'],'confirmation_state':gate_evidence['confirmation']['state'],'risk_state':gate_evidence['risk']['state'],'execution_enabled':False,'orders_placed':False
    }
    try: JOURNAL.append_decision(record)
    except ValueError as e:
     if str(e)!='duplicate event_id': raise
    # Research-only scoring of the locked candidate, separate from operational approval.
    # Final gate remains fail-closed; this path records hypothetical outcomes only.
    if proposal.decision in ('LONG','SHORT') and proposal.entry is not None:
     candidate_event_id=f"hes-v2-candidate-{src['symbol']}-15m-{now}"
     t={'candidate_time':now,'candidate_event_id':candidate_event_id,'direction':proposal.direction,'entry':proposal.entry,'stop_loss':proposal.stop_loss,'take_profit':proposal.take_profit,'rr':proposal.rr,'final_gate_decision':d.decision,'final_gate_reasons':list(d.reasons),'preapproval_paper_eligible':preapproval['eligible'],'preapproval_paper_status':preapproval['status'],'preapproval_paper_reasons':preapproval['reasons']}
     st['active'].append(t);append(CAND,{'schema':'hes_strategy_policy_v2_paper_candidate','candidate_event_id':candidate_event_id,'event_id':candidate_event_id,'evaluation_mode':'PREAPPROVAL_PAPER_ONLY','preapproval_paper_eligible':preapproval['eligible'],'preapproval_paper_status':preapproval['status'],'preapproval_paper_reasons':preapproval['reasons'],'entry_context':entry_context,'gate_evidence':gate_evidence,'final_gate_decision':d.decision,'final_gate_reasons':list(d.reasons),**t,'policy_version':POLICY_VERSION,'observed_at':datetime.now(timezone.utc).isoformat(),'source':src['source'],'symbol':src['symbol'],'execution_enabled':False,'orders_placed':False})
     append(BASE/'trade_journal_v2.jsonl',{'schema':'hes_trade_journal_paper_candidate_v1','event_id':candidate_event_id,'candidate_event_id':candidate_event_id,'observed_at':datetime.now(timezone.utc).isoformat(),'candle_close_time':now,'symbol':src['symbol'],'timeframe':'15m','direction':proposal.direction,'decision':'PAPER_CANDIDATE','entry':proposal.entry,'stop_loss':proposal.stop_loss,'take_profit':proposal.take_profit,'rr':proposal.rr,'quality_score':proposal.quality_score,'proposal_reasons':list(proposal.reasons),'final_gate_decision':d.decision,'final_gate_reasons':list(d.reasons),'preapproval_paper_eligible':preapproval['eligible'],'preapproval_paper_status':preapproval['status'],'preapproval_paper_reasons':preapproval['reasons'],'entry_context':entry_context,'gate_evidence':gate_evidence,'outcome':None,'closed_at':None,'execution_enabled':False,'orders_placed':False})
    st['last_seen']=now
   resolved=st['wins']+st['losses'];wr=round(100*st['wins']/resolved,2) if resolved else None
   pm=performance_metrics()
   # Official performance is derived only from the append-only 1m precision ledger.
   # The 15m preapproval journal remains a separate diagnostic cohort.
   acceptance=evaluate_acceptance(root=CODE_ROOT,data_root=DATA_ROOT,metrics=pm,candidates=[],independent_oos=None)
   report={'schema':'hes_strategy_policy_v2_forward_evaluation','policy_version':POLICY_VERSION,'updated_at':datetime.now(timezone.utc).isoformat(),'source':src['source'],'symbol':src['symbol'],'closed_15m_candle_time':now,'active_candidates':len(st['active']),'wins':pm['eligible_wins'],'losses':pm['eligible_losses'],'timeouts':pm['eligible_timeouts'],'ambiguous_losses':st['ambiguous_losses'],'resolved_win_rate_pct':pm['eligible_win_rate_pct'],'performance_metrics':pm,'research_only_raw_wins':st['wins'],'research_only_raw_losses':st['losses'],'final_gate_version':'hes-strategy-policy-final-gate-v1.0.0','gate_pipeline_version':'hes-strategy-gate-pipeline-v1.0.0','market_data_provenance':market_data_provenance,'latest_gate_evidence':gate_evidence,'directional_candidates_blocked_until_gates_approved':True,'target_win_rate_pct':acceptance['target_win_rate_pct'],'target_met':acceptance['status']=='PASS','precision_entry_paper_target_met':acceptance['status']=='PASS','minimum_resolved_trades_for_target_claim':acceptance['minimum_resolved_closed_trades'],'target_policy_status':acceptance['status'],'paper_performance_scope':acceptance['performance_cohort'],'signal_quality_acceptance':acceptance,'execution_enabled':False,'orders_placed':False,'caveat':'Acceptance contract is enforced fail-closed. Official paper acceptance uses only the append-only 1m precision-entry READY ledger: strictly >90% over at least 100 resolved closed trades, <=3 actionable entries per UTC day (cap, never quota), clean event/candidate/outcome linkage, verified fees/slippage, and independent out-of-sample evidence. 15m preapproval and research-only cohorts are baseline diagnostics only. Official final-gate approval remains separate; no live trading.'}
   STATE.write_text(json.dumps(st,indent=2)+'\n');REPORT.write_text(json.dumps(report,indent=2)+'\n')
   print(json.dumps({'candle':now,'active':len(st['active']),'wins':st['wins'],'losses':st['losses'],'timeouts':st['timeouts'],'win_rate_pct':wr,'decision':d.decision if new_candle else 'TRACKING','gate_version':d.gate_version} if new_candle else {'candle':now,'active':len(st['active']),'wins':st['wins'],'losses':st['losses'],'timeouts':st['timeouts'],'win_rate_pct':wr,'decision':'TRACKING'}),flush=True)
  except Exception as e:print(json.dumps({'error':type(e).__name__+':'+str(e)[:180],'decision':'NO_TRADE','execution_enabled':False}),flush=True)
  time.sleep(30)
if __name__=='__main__':main()

