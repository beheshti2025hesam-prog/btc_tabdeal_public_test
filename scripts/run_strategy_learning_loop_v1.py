#!/usr/bin/env python3
"""Read-only evidence-driven learning loop. Proposes hypotheses; never edits policy or executes orders."""
import json,time,hashlib,uuid
from pathlib import Path
from datetime import datetime,timezone
import sys
CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
from forward.strategy_v2_run_provenance_v1 import validate_run_manifest
from forward.strategy_family_router_v1 import TREND_BREAKOUT_V2, RANGE_MEAN_REVERSION_RESEARCH_V1
from forward.trade_journal_view_v1 import read_decision_journal, JournalProjectionError
ROOT=DATA_ROOT; DATA=ROOT/'data/forward'
sys.path.insert(0, str(CODE_ROOT/'scripts'))
from forward.neutral_decision_outcomes_v1 import run as update_neutral_outcomes
from run_decision_report_24h_v1 import build_report as update_decision_report
from run_no_trade_decision_audit_v1 import build_audit as update_no_trade_audit
from run_matured_no_trade_validation_v1 import build as update_matured_no_trade_validation
JOURNAL=DATA/'trade_journal_v2.jsonl'; OUTCOMES=DATA/'strategy_policy_v2_eval_outcomes.jsonl'; CANDIDATES=DATA/'strategy_policy_v2_eval_candidates.jsonl'; NEUTRAL_OUTCOMES=DATA/'neutral_decision_outcomes_v1.jsonl'
REPORT=DATA/'strategy_learning_v1_report.json'; HYPOTHESES=DATA/'strategy_learning_v1_hypotheses.jsonl'; STATE=DATA/'strategy_learning_v1_state.json'
LEARNING_RUN_ID='HESLEARN-'+uuid.uuid4().hex
LEARNING_CYCLE=0
def read_strategy_run_provenance():
 p=DATA/'strategy_policy_v2_eval_report.json'; manifests=DATA/'strategy_policy_v2_run_manifests_v2.jsonl'
 try:
  report=json.loads(p.read_text())
  stamp=datetime.fromisoformat(str(report.get('updated_at','')).replace('Z','+00:00'))
  if stamp.tzinfo is None or stamp.utcoffset() is None: return {'status':'INVALID_TIMESTAMP','fresh':False}
  age=(datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
  matches=[row for row in read_jsonl(manifests) if row.get('run_id')==report.get('run_id')]
  if len(matches)!=1 or not validate_run_manifest(matches[0]):
   return {'status':'RUN_MANIFEST_MISSING_OR_INVALID','fresh':False,'report_updated_at':report.get('updated_at')}
  manifest=matches[0]
  if (manifest.get('run_manifest_sha256')!=report.get('run_manifest_sha256')
      or report.get('code_release_id')!=manifest.get('code_release_id')
      or report.get('source_hashes')!=manifest.get('source_hashes')
      or any(report.get(key)!=value for key,value in manifest.get('source_hashes',{}).items())):
   return {'status':'RUN_MANIFEST_REPORT_MISMATCH','fresh':False,'report_updated_at':report.get('updated_at')}
  return {'status':'VERIFIED','fresh':-60<=age<=1800,'report_updated_at':report.get('updated_at'),
          'run_id':manifest.get('run_id'),'service_name':manifest.get('service_name'),
          'code_release_id':manifest.get('code_release_id'),'run_manifest_sha256':manifest.get('run_manifest_sha256'),
          'source_hashes':manifest.get('source_hashes')}
 except (OSError,ValueError,TypeError,json.JSONDecodeError):
  return {'status':'MISSING_OR_INVALID','fresh':False}

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
  report=json.loads(p.read_text())
  stamp=datetime.fromisoformat(str(report.get('updated_at','')).replace('Z','+00:00'))
  if stamp.tzinfo is None or stamp.utcoffset() is None:
   return {}
  age=(datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
  if age < -60 or age > 1800:
   return {}
  value=report.get('signal_quality_acceptance',{})
  if not isinstance(value,dict) or value.get('schema')!='hes_signal_quality_acceptance_result_v1':
   return {}
  return value
 except (OSError,ValueError,TypeError,json.JSONDecodeError):
  return {}

FAMILY_PROFILES = {
    TREND_BREAKOUT_V2.family_id: TREND_BREAKOUT_V2,
    RANGE_MEAN_REVERSION_RESEARCH_V1.family_id: RANGE_MEAN_REVERSION_RESEARCH_V1,
}

def _canonical_report_sha(value):
    payload = {key: item for key, item in value.items() if key != 'report_sha256'}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def read_family_paper_reconciliation():
    path = DATA / 'strategy_family_paper_reconciliation_v1.json'
    if not path.is_file():
        return {'status':'MISSING','fresh':False,'reason':'REPORT_NOT_FOUND','families':{}}
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(report, dict) or report.get('schema') != 'hes_strategy_family_paper_reconciliation_v1':
            return {'status':'INVALID','fresh':False,'reason':'REPORT_SCHEMA_INVALID','families':{}}
        stamp = datetime.fromisoformat(str(report.get('updated_at','')).replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return {'status':'INVALID','fresh':False,'reason':'REPORT_TIMESTAMP_INVALID','families':{}}
        if report.get('report_sha256') != _canonical_report_sha(report):
            return {'status':'INVALID','fresh':False,'reason':'REPORT_HASH_MISMATCH','families':{}}
        expected = set(FAMILY_PROFILES)
        summaries = report.get('families')
        details = report.get('family_reports')
        if not isinstance(summaries, dict) or not isinstance(details, dict) or set(summaries) != expected or set(details) != expected:
            return {'status':'INVALID','fresh':False,'reason':'FAMILY_REPORT_SET_INVALID','families':{}}
        if (report.get('acceptance_is_independent_per_family') is not True
                or report.get('timestamp_fallback_matching') is not False
                or report.get('execution_enabled') is not False
                or report.get('orders_placed') is not False
                or report.get('risk_gate_modified') is not False
                or report.get('live_trading_authorized') is not False):
            return {'status':'INVALID','fresh':False,'reason':'SAFETY_OR_COHORT_BOUNDARY_INVALID','families':{}}
        source_hashes = report.get('source_hashes')
        if not isinstance(source_hashes, dict):
            return {'status':'INVALID','fresh':False,'reason':'SOURCE_HASH_SET_INVALID','families':{}}
        expected_sources = {
            'decision_journal_sha256': sha(DATA/'trade_journal_v2.jsonl'),
            'candidate_ledger_sha256': sha(DATA/'strategy_family_paper_candidates_v1.jsonl'),
            'outcome_ledger_sha256': sha(DATA/'strategy_family_paper_outcomes_v1.jsonl'),
            'paper_cost_context_sha256': sha(ROOT/'forward/paper_risk_context_v1.json'),
        }
        if any(source_hashes.get(key) != value for key, value in expected_sources.items()):
            return {'status':'INVALID','fresh':False,'reason':'SOURCE_HASH_MISMATCH','families':{}}
        market_digest = source_hashes.get('market_data_rows_sha256')
        if not isinstance(market_digest, str) or len(market_digest) != 64 or any(c not in '0123456789abcdef' for c in market_digest):
            return {'status':'INVALID','fresh':False,'reason':'MARKET_DATA_HASH_INVALID','families':{}}
        family_summary = {}
        for family_id, profile in FAMILY_PROFILES.items():
            summary = summaries[family_id]
            detail = details[family_id]
            if (not isinstance(summary, dict) or not isinstance(detail, dict)
                    or summary.get('family_id') != family_id
                    or summary.get('family_version') != profile.version
                    or detail.get('schema') != 'hes_strategy_family_evaluation_report_v1'
                    or detail.get('family_id') != family_id
                    or detail.get('family_version') != profile.version
                    or detail.get('cohort_family_ids') != [family_id]
                    or detail.get('execution_enabled') is not False
                    or detail.get('orders_placed') is not False
                    or detail.get('source_hashes') != source_hashes
                    or detail.get('report_sha256') != _canonical_report_sha(detail)):
                return {'status':'INVALID','fresh':False,'reason':'FAMILY_IDENTITY_OR_HASH_INVALID','families':{}}
            family_summary[family_id] = {
                'family_id': family_id,
                'family_version': profile.version,
                'candidate_count': summary.get('candidate_count'),
                'resolved_outcome_count': summary.get('resolved_outcome_count'),
                'pending_candidate_count': summary.get('pending_candidate_count'),
                'acceptance_eligible_candidate_count': summary.get('acceptance_eligible_candidate_count'),
                'acceptance_eligible_metrics': summary.get('acceptance_eligible_metrics'),
                'research_shadow_metrics': summary.get('research_shadow_metrics'),
                'acceptance_status': summary.get('acceptance_status'),
                'acceptance_blockers': summary.get('acceptance_blockers'),
            }
        acceptance = report.get('family_acceptance')
        if (not isinstance(acceptance, dict)
                or acceptance.get('schema') != 'hes_strategy_family_acceptance_result_v1'
                or acceptance.get('activation_authorized') is not False
                or acceptance.get('execution_enabled') is not False
                or acceptance.get('orders_placed') is not False):
            return {'status':'INVALID','fresh':False,'reason':'FAMILY_ACCEPTANCE_BOUNDARY_INVALID','families':{}}
        age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        if age < -60 or age > 1800:
            return {'status':'STALE','fresh':False,'reason':'REPORT_OUTSIDE_FRESHNESS_WINDOW','age_seconds':round(age,1),'updated_at':report.get('updated_at'),'report_sha256':report.get('report_sha256'),'families':family_summary,'family_acceptance_status':acceptance.get('status')}
        return {
            'status':'VERIFIED','fresh':True,'reason':None,'age_seconds':round(age,1),
            'updated_at':report.get('updated_at'),'report_sha256':report.get('report_sha256'),
            'candidate_records':report.get('candidate_records'),'outcome_records':report.get('outcome_records'),
            'family_acceptance_status':acceptance.get('status'),'families':family_summary,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, OverflowError):
        return {'status':'INVALID','fresh':False,'reason':'REPORT_READ_OR_VALIDATION_ERROR','families':{}}

def family_cohort_hypotheses(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('fresh') is not True:
        status = snapshot.get('status','MISSING') if isinstance(snapshot, dict) else 'MISSING'
        return [{
            'hypothesis_id':'family-paper-cohort-integrity-monitor-v1',
            'type':'FAMILY_COHORT_PIPELINE_DIAGNOSTIC',
            'report_status':status,
            'status':'HYPOTHESIS_ONLY',
            'proposal':'Verify the family-isolated paper cohort report is produced from the canonical Gate.io 15m decision journal with valid hashes and freshness. Do not infer missing trades, merge family cohorts, alter gates, or authorize execution.',
        }]
    result = []
    for family_id, family in sorted(snapshot.get('families',{}).items()):
        if family.get('acceptance_status') == 'PASS':
            continue
        result.append({
            'hypothesis_id':f'family-paper-cohort-{family_id}-monitor-v1',
            'type':'FAMILY_PAPER_COHORT_ACCEPTANCE_MONITOR',
            'family_id':family_id,
            'candidate_records':family.get('candidate_count'),
            'resolved_outcomes':family.get('resolved_outcome_count'),
            'acceptance_blockers':family.get('acceptance_blockers') or [],
            'proposal':'Continue isolated, forward-only paper collection for this family. Require at least 100 eligible resolved trades, strictly above 90% win rate, positive net expectancy, profit factor above 1, verified fees/slippage, clean provenance/linkage, independent out-of-sample evidence, and the global three-signal daily cap. Never pool families or relax the shared Risk Gate.',
            'status':'HYPOTHESIS_ONLY',
        })
    return result
def family_research_hypotheses():
    """Summarize four-family research-only evidence from validated decision projections."""
    try:
        journal = read_decision_journal(JOURNAL, limit=100, expected_source='gateio_public_spot',
                                        expected_symbol='BTC_USDT', require_execution_off=True)
        if journal.get('status') not in ('VERIFIED', 'EMPTY'):
            raise ValueError('DECISION_JOURNAL_NOT_VERIFIED')
        assessments = [
            event.get('strategy_family_research_assessment')
            for event in journal.get('events', [])
            if isinstance(event.get('strategy_family_research_assessment'), dict)
        ]
    except (OSError, ValueError, TypeError, JournalProjectionError):
        return [{
            'hypothesis_id':'four-family-research-journal-integrity-v1',
            'type':'FOUR_FAMILY_RESEARCH_JOURNAL_DIAGNOSTIC',
            'status':'HYPOTHESIS_ONLY',
            'proposal':'Verify canonical journal integrity and four-family evidence provenance before interpreting family outcomes. Do not infer missing features, tune thresholds or authorize trades.',
        }]
    assessed = [item for item in assessments if item.get('status') == 'ASSESSED']
    if not assessed:
        return [{
            'hypothesis_id':'four-family-research-evidence-availability-v1',
            'type':'FOUR_FAMILY_RESEARCH_EVIDENCE_AVAILABILITY',
            'journal_assessment_records':len(assessments),
            'status':'HYPOTHESIS_ONLY',
            'proposal':'Continue collecting validated closed Gate.io 15m evidence for all four families. Do not synthesize missing feature values or change strategy thresholds.',
        }]
    family_ids = ('trend_continuation','breakout_retest','range_reversion','volatility_expansion')
    hypotheses = []
    for family_id in family_ids:
        samples = [item['families'][family_id] for item in assessed
                   if isinstance(item.get('families'), dict) and isinstance(item['families'].get(family_id), dict)]
        if not samples:
            continue
        latest = samples[0]
        failures = {}
        eligible_count = 0
        for sample in samples:
            if sample.get('status') == 'RESEARCH_ELIGIBLE':
                eligible_count += 1
            for feature, passed in sample.get('features', {}).items():
                if passed is False:
                    failures[feature] = failures.get(feature, 0) + 1
        hypotheses.append({
            'hypothesis_id':f'four-family-research-{family_id}-diagnostic-v1',
            'type':'FOUR_FAMILY_RESEARCH_FEATURE_ATTRIBUTION',
            'family_id':family_id,
            'assessed_decisions':len(samples),
            'research_eligible_decisions':eligible_count,
            'latest_status':latest.get('status'),
            'latest_direction':latest.get('direction'),
            'feature_failure_counts':dict(sorted(failures.items(), key=lambda item:(-item[1],item[0]))),
            'status':'HYPOTHESIS_ONLY',
            'proposal':'Review repeated feature failures against raw closed-candle evidence, regime labels and source quality. Do not relax thresholds, invent missing fields, promote a family, or count research eligibility as a trade.',
        })
    return hypotheses


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

def economic_counts(rows, candidate_by_row_id=None, cost_side=0.0):
    """Score resolved outcomes using the same linked-candidate fallbacks as the evaluator."""
    candidate_by_row_id = candidate_by_row_id or {}
    wins=losses=flats=timeouts=unscorable=0
    for r in rows:
        outcome=str(r.get('outcome','')).lower()
        if outcome not in ('wins','losses','timeouts'):
            continue
        if outcome=='timeouts':
            timeouts+=1
        candidate=candidate_by_row_id.get(id(r),{})
        direction=str(r.get('direction') or candidate.get('direction') or '')
        entry=r.get('entry',candidate.get('entry'))
        stop=r.get('stop_loss',candidate.get('stop_loss'))
        target=r.get('take_profit',candidate.get('take_profit'))
        exit_price=r.get('exit_price')
        if exit_price is None:
            reason=str(r.get('reason') or r.get('outcome_reason') or '')
            if 'STOP_LOSS' in reason or 'STOP_AND_TARGET' in reason:
                exit_price=stop
            elif 'TAKE_PROFIT' in reason:
                exit_price=target
            else:
                exit_price=r.get('exit_close')
        try:
            entry=float(entry); exit_price=float(exit_price); stop=float(stop)
            if entry<=0 or exit_price<=0 or stop<=0 or direction not in ('LONG','SHORT'):
                raise ValueError()
            gross=(exit_price-entry) if direction=='LONG' else (entry-exit_price)
            net=gross-(entry+exit_price)*cost_side
        except (TypeError,ValueError):
            unscorable+=1
            continue
        if net>0:
            wins+=1
        elif net<0:
            losses+=1
        else:
            flats+=1
    resolved=wins+losses+flats
    return {'wins':wins,'losses':losses,'flats':flats,'timeouts':timeouts,'resolved':resolved,
            'win_rate_pct':round(100*wins/resolved,2) if resolved else None,'unscorable':unscorable}

def win_rate_target_met(*, resolved, win_rate_pct, unmatched_outcomes, ambiguous_outcomes, unscorable_outcomes, minimum_resolved=100, target_pct=90.0):
    return bool(resolved >= minimum_resolved and win_rate_pct is not None and win_rate_pct > target_pct
                and unmatched_outcomes == 0 and ambiguous_outcomes == 0 and unscorable_outcomes == 0)

def main():
 global LEARNING_CYCLE
 while True:
  try:
   LEARNING_CYCLE += 1
   learning_cycle_id=f'{LEARNING_RUN_ID}:{LEARNING_CYCLE}'
   strategy_run_provenance=read_strategy_run_provenance()
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
   family_cohort_status=read_family_paper_reconciliation()
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
   candidate_by_row_id={id(row):candidate for row,candidate in linked_outcomes}
   ec=economic_counts(eligible_outcomes,candidate_by_row_id,cost_side); pc=economic_counts(preapproval_outcomes,candidate_by_row_id,cost_side); rc=economic_counts(research_only_outcomes,candidate_by_row_id,cost_side)
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
   hypotheses.extend(family_cohort_hypotheses(family_cohort_status))
   four_family_research_hypotheses=family_research_hypotheses()
   hypotheses.extend(four_family_research_hypotheses)
   for reason,n in sorted(rejected.items(),key=lambda x:(-x[1],x[0]))[:10]:
    hypotheses.append({'hypothesis_id':'gate-'+hashlib.sha256(reason.encode()).hexdigest()[:10],'type':'GATE_ATTRIBUTION_REVIEW','gate_reason':reason,'observations':n,'proposal':'Inspect feature availability and rejection calibration; do not relax the gate without a preregistered out-of-sample test.','status':'HYPOTHESIS_ONLY'})
    acceptance=read_acceptance()
    precision_resolved=int(acceptance.get('resolved_closed_trade_count',0) or 0)
    if acceptance.get('status')!='PASS':
     hypotheses.append({'hypothesis_id':'precision-entry-acceptance-monitor-v1','type':'PRECISION_ENTRY_ACCEPTANCE_MONITOR','resolved_trades':precision_resolved,'proposal':'Continue forward-only 1m precision-entry paper collection. Official acceptance requires strictly >90% win rate over at least 100 resolved closed 1m READY candidates, no more than 3 actionable entries per UTC day, verified fee/slippage provenance, clean event/candidate/outcome linkage, and independent out-of-sample evidence. 15m preapproval and research-only outcomes are baseline diagnostics and do not count.','status':'HYPOTHESIS_ONLY'})
   if not candidates: hypotheses.append({'hypothesis_id':'candidate-flow-check','type':'CANDIDATE_FLOW_DIAGNOSTIC','proposal':'Check whether locked policy conditions generate candidates across observed regimes; never fabricate trades or bypass risk gates.','status':'HYPOTHESIS_ONLY'})
   neutral_complete=[r for r in neutral_outcomes if r.get('horizon_complete') is True]
   neutral_classes={}
   for row in neutral_complete:
    cls=row.get('outcome_class','UNKNOWN'); neutral_classes[cls]=neutral_classes.get(cls,0)+1
   if neutral_complete:
    hypotheses.append({'hypothesis_id':'neutral-decision-outcome-review-v1','type':'NO_TRADE_COUNTERFACTUAL_REVIEW','observations':len(neutral_complete),'outcome_classes':neutral_classes,'proposal':'Compare NO_TRADE gate reasons with forward-only outcomes; separate avoided losses, plausible missed opportunities, directionless context and ambiguous candles. No policy change without independent out-of-sample evidence.','status':'HYPOTHESIS_ONLY'})
   old=read_jsonl(HYPOTHESES); ids={x.get('hypothesis_id') for x in old}; new=[h for h in hypotheses if h['hypothesis_id'] not in ids]
   with HYPOTHESES.open('a') as f:
    for h in new: f.write(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'learning_run_id':LEARNING_RUN_ID,'learning_cycle_id':learning_cycle_id,**h},sort_keys=True)+'\n')
    f.flush()
   # Reuse the canonical, freshness-checked precision-ledger acceptance result.
   acceptance=read_acceptance()
   report={'schema':'hes_strategy_learning_loop_v1','updated_at':datetime.now(timezone.utc).isoformat(),'learning_run_id':LEARNING_RUN_ID,'learning_cycle_id':learning_cycle_id,'learning_code_release_id':CODE_ROOT.name,'learning_source_sha256':sha(CODE_ROOT/'scripts/run_strategy_learning_loop_v1.py'),'strategy_run_provenance':strategy_run_provenance,'mode':'READ_ONLY_HYPOTHESIS_ONLY','policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False,'decision_records':len(decisions),'decision_counts':counts,'gate_rejection_counts':rejected,'candidate_records':len(candidates),'neutral_tracker_status':neutral_tracker_status,'decision_report_24h_status':({'generated_at':decision_report_24h_status.get('generated_at'),'decision_counts':decision_report_24h_status.get('decision_counts'),'no_trade_decisions_in_window':decision_report_24h_status.get('no_trade_decisions_in_window')} if 'schema' in decision_report_24h_status else decision_report_24h_status),'no_trade_decision_audit_status':({'generated_at':no_trade_audit_status.get('generated_at'),'unique_no_trade_decisions':no_trade_audit_status.get('unique_no_trade_decisions'),'screen_status_counts':no_trade_audit_status.get('screen_status_counts')} if 'schema' in no_trade_audit_status else no_trade_audit_status),'matured_no_trade_validation_status':({'generated_at':matured_no_trade_validation_status.get('generated_at'),'decisions_in_matured_cohort':matured_no_trade_validation_status.get('decisions_in_matured_cohort'),'complete_gap_free_24h_decisions':matured_no_trade_validation_status.get('complete_gap_free_24h_decisions'),'directional_counterfactuals':matured_no_trade_validation_status.get('directional_counterfactuals'),'preapproval_hold_counterfactuals':matured_no_trade_validation_status.get('preapproval_hold_counterfactuals'),'rejected_proposal_counterfactuals':matured_no_trade_validation_status.get('rejected_proposal_counterfactuals'),'unverified_proposal_counterfactuals':matured_no_trade_validation_status.get('unverified_proposal_counterfactuals'),'decision_quality_buckets_by_horizon':matured_no_trade_validation_status.get('decision_quality_buckets_by_horizon'),'decision_quality_methodology':matured_no_trade_validation_status.get('decision_quality_methodology'),'validation_status_counts':matured_no_trade_validation_status.get('validation_status_counts'),'horizon_quality_counts':matured_no_trade_validation_status.get('horizon_quality_counts'),'tracker_boundary_mismatches':matured_no_trade_validation_status.get('tracker_boundary_mismatches')} if 'schema' in matured_no_trade_validation_status else matured_no_trade_validation_status),'neutral_decision_outcome_records':len(neutral_outcomes),'neutral_decision_outcome_complete_records':len(neutral_complete),'neutral_decision_outcome_class_counts':neutral_classes,'neutral_outcome_evidence_sha256':sha(NEUTRAL_OUTCOMES),'resolved_outcomes':resolved,'wins':wins,'losses':losses,'flats':flats,'timeouts':timeouts,'unscorable_eligible_outcomes':ec['unscorable'],'preapproval_paper_outcomes':len(preapproval_outcomes),'preapproval_paper_resolved':pc['resolved'],'preapproval_paper_wins':pc['wins'],'preapproval_paper_losses':pc['losses'],'preapproval_paper_flats':pc['flats'],'preapproval_paper_timeouts':pc['timeouts'],'preapproval_paper_win_rate_pct':pc['win_rate_pct'],'preapproval_paper_unscorable_outcomes':pc['unscorable'],'precision_entry_paper_target_met':acceptance.get('status')=='PASS','precision_entry_resolved_closed_trades':int(acceptance.get('resolved_closed_trade_count',0) or 0),'precision_entry_win_rate_pct':acceptance.get('observed_win_rate_pct'),'acceptance_report_fresh':bool(acceptance),'win_rate_pct':wr,'decisive_win_rate_pct':round(100*wins/(wins+losses),2) if wins+losses else None,'cost_model':{'status':'ASSUMPTION_BASED' if cost_side>0 else 'UNAVAILABLE','fee_fraction_per_side':float(cost_cfg.get('fee_fraction_per_side',0) or 0),'slippage_fraction_per_side':float(cost_cfg.get('slippage_fraction_per_side',0) or 0),'note':'Simulation assumptions only; not verified exchange/account costs.'},'performance_scope':'GATE_APPROVED_ONLY','research_only_outcomes':len(research_only_outcomes),'research_only_wins':research_wins,'research_only_losses':research_losses,'research_only_timeouts':research_timeouts,'excluded_rejected_outcomes':len(research_only_outcomes),'outcomes_by_direction':outcome_by_direction,'candidate_outcome_match_count':matched_outcomes,'unmatched_outcome_count':unmatched_outcomes,'ambiguous_legacy_outcome_match_count':ambiguous_outcomes,'preapproval_paper_candidate_count':sum(r.get('preapproval_paper_eligible') is True for r in candidates),'gate_approved_candidate_count':sum(r.get('final_gate_decision') in ('LONG','SHORT') for r in candidates),'gate_rejected_candidate_count':sum(r.get('final_gate_decision') not in ('LONG','SHORT') for r in candidates),'unresolved_candidate_count':unresolved_candidates,'target_win_rate_pct':acceptance.get('target_win_rate_pct'),'minimum_resolved_trades_for_claim':acceptance.get('minimum_resolved_closed_trades'),'target_met':acceptance.get('status')=='PASS','target_policy_status':acceptance.get('status','NOT_MET'),'paper_performance_scope':acceptance.get('performance_cohort','PRECISION_ENTRY_PAPER_ELIGIBLE'),'signal_quality_acceptance':acceptance,'family_paper_cohort_status':family_cohort_status,'four_family_research_hypotheses':four_family_research_hypotheses,'evidence_sha256':{'family_paper_cohort':sha(DATA/'strategy_family_paper_reconciliation_v1.json'),'journal':sha(JOURNAL),'outcomes':sha(OUTCOMES),'candidates':sha(CANDIDATES),'neutral_outcomes':sha(NEUTRAL_OUTCOMES),'precision_events':sha(DATA/'precision_entry_events_v1.jsonl'),'precision_candidates':sha(DATA/'precision_entry_candidates_v1.jsonl'),'precision_outcomes':sha(DATA/'precision_entry_outcomes_v1.jsonl'),'precision_report':sha(DATA/'precision_entry_journal_report_v1.json'),'precision_cost_model':sha(DATA/'precision_entry_cost_model_v1.json'),'precision_independent_oos':sha(DATA/'precision_entry_independent_oos_evidence_v1.json'),'strategy_evaluator_report':sha(DATA/'strategy_policy_v2_eval_report.json'),'strategy_run_manifest_ledger':sha(DATA/'strategy_policy_v2_run_manifests_v2.jsonl'),'legacy_strategy_runs_ledger':sha(DATA/'strategy_policy_v2_runs.jsonl'),'signal_quality_contract':sha(CODE_ROOT/'docs/execution/SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json'),'matured_no_trade_validation':sha(DATA/'matured_no_trade_validation_v1.json'),'decision_report_24h':sha(DATA/'decision_report_24h_v1.json')},'new_hypotheses_added':len(new),'hypotheses_total':len(old)+len(new),'limitations':['NO_TRADE counterfactual outcomes are observational and do not prove causality','Directionless NO_TRADE records are market-context only, not invented trades','Raw neutral outcome class counts include gate-rejected proposal counterfactuals and directionless context; use gate-qualified matured buckets for attribution.','Net outcome estimates use explicit unverified simulation fee/slippage assumptions, not verified exchange/account costs','No automatic threshold tuning','No policy changes','No live orders','Gate counts are not causal attribution','Official acceptance uses only the append-only 1m precision-entry READY ledger; 15m preapproval and research-only outcomes are excluded; stale or missing acceptance reports fail closed','Cost-adjusted expectancy requires reliable fill and cost model','Stable candidate IDs are preferred; legacy timestamp fallback is accepted only when unique','Cost-adjusted results use explicit unverified simulation fee/slippage assumptions and are not live performance']}
   REPORT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); STATE.write_text(json.dumps({'last_updated':report['updated_at'],'last_evidence':report['evidence_sha256']},indent=2)+'\n')
   print(json.dumps({'updated_at':report['updated_at'],'decisions':len(decisions),'candidates':len(candidates),'resolved':resolved,'win_rate_pct':wr,'new_hypotheses':len(new),'target_met':report['target_met'],'policy_mutation_enabled':False}),flush=True)
  except Exception as e: print(json.dumps({'error':type(e).__name__+':'+str(e)[:200],'policy_mutation_enabled':False,'execution_enabled':False}),flush=True)
  time.sleep(300)
if __name__=='__main__': main()