#!/usr/bin/env python3
"""Generate a strict rolling 24h HES decision report; read-only, no trading."""
from __future__ import annotations
import json, hashlib, argparse, importlib.util, sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
ROOT=DATA_ROOT
DATA=ROOT/'data/forward'
JOURNAL=DATA/'trade_journal_v2.jsonl'
NEUTRAL=DATA/'neutral_decision_outcomes_v1.jsonl'
CANDIDATES=DATA/'strategy_policy_v2_eval_candidates.jsonl'
OUTCOMES=DATA/'strategy_policy_v2_eval_outcomes.jsonl'
REPORT=DATA/'decision_report_24h_v1.json'
MATURITY_VALIDATOR=CODE_ROOT/'scripts/run_matured_no_trade_validation_v1.py'

def parse_dt(v):
    if isinstance(v, bool) or v is None or v == '': raise ValueError('MISSING_OR_INVALID_TIMESTAMP')
    if isinstance(v, (int, float)): return datetime.fromtimestamp(v, timezone.utc)
    dt = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    # Naive timestamps are explicitly interpreted as UTC; never depend on host TZ.
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def read_jsonl(path):
    if not path.exists(): return []
    rows=[]
    for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as e: raise ValueError(f'MALFORMED_JSONL:{path.name}:{n}') from e
        if not isinstance(row,dict): raise ValueError(f'INVALID_RECORD:{path.name}:{n}')
        rows.append(row)
    return rows

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def build_matured_validation(now):
    """Refresh and summarize the independent 24-48h NO_TRADE validation.

    Paths are rebound to this report's data root so tests and isolated runs cannot
    accidentally read or write production evidence outside their configured DATA.
    """
    spec=importlib.util.spec_from_file_location('hes_matured_no_trade_validation_for_report', MATURITY_VALIDATOR)
    if spec is None or spec.loader is None: raise RuntimeError('VALIDATOR_IMPORT_FAILED')
    validator=importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)
    validator.DATA=DATA
    validator.JOURNAL=JOURNAL
    validator.CANDLES=DATA/'global_market_candles_v1.jsonl'
    validator.NEUTRAL=NEUTRAL
    validator.REPORT=DATA/'matured_no_trade_validation_v1.json'
    validator.RECORDS=DATA/'matured_no_trade_validation_v1.jsonl'
    result=validator.build(now)
    return {
      'status':'OK','schema':result.get('schema'),'generated_at':result.get('generated_at'),
      'cohort_age_hours':result.get('cohort_age_hours'),
      'decisions_in_matured_cohort':result.get('decisions_in_matured_cohort'),
      'validation_status_counts':result.get('validation_status_counts'),
      'complete_gap_free_24h_decisions':result.get('complete_gap_free_24h_decisions'),
      'horizon_quality_counts':result.get('horizon_quality_counts'),
      'decision_quality_buckets_by_horizon':result.get('decision_quality_buckets_by_horizon'),
      'decision_quality_methodology':result.get('decision_quality_methodology'),
      'limitations':result.get('limitations'),
      'directional_counterfactuals':result.get('directional_counterfactuals'),
      'preapproval_hold_counterfactuals':result.get('preapproval_hold_counterfactuals'),
      'rejected_proposal_counterfactuals':result.get('rejected_proposal_counterfactuals'),
      'unverified_proposal_counterfactuals':result.get('unverified_proposal_counterfactuals'),
      'tracker_boundary_comparisons':result.get('tracker_boundary_comparisons'),
      'tracker_boundary_mismatches':result.get('tracker_boundary_mismatches'),
      'cost_model':result.get('decision_quality_methodology',{}).get('cost_model'),
      'source_sha256':result.get('source_sha256'),
      'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False,
      'interpretation':'Hypotheses are observational counterfactuals, not proof of causality or net profitability.'
    }

def build_report(now=None):
    now=parse_dt(now if now is not None else datetime.now(timezone.utc))
    start=now-timedelta(hours=24)
    all_journal=read_jsonl(JOURNAL)
    neutral_all=read_jsonl(NEUTRAL)
    candidates_all=read_jsonl(CANDIDATES)
    outcomes_all=read_jsonl(OUTCOMES)
    invalid_timestamps=0
    journal=[]
    for r in all_journal:
        try: ts=parse_dt(r.get('observed_at'))
        except Exception: invalid_timestamps+=1; continue
        if start <= ts <= now: journal.append((ts,r))
    decisions=[r for _,r in journal if r.get('decision') in ('LONG','SHORT','NO_TRADE')]
    counts=Counter(r.get('decision','UNKNOWN') for r in decisions)
    reasons=Counter()
    for r in decisions:
        raw=r.get('gate_reasons') or r.get('final_gate_reasons') or r.get('no_trade_reason') or r.get('final_gate_reasons') or []
        if isinstance(raw,str): raw=[x for x in raw.split('|') if x]
        for reason in raw:
            if reason: reasons[str(reason)]+=1
    # Link follow-ups only to unique NO_TRADE event IDs. Duplicate journal rows or
    # duplicate horizon records must not inflate completion or erase pending horizons.
    no_trade_ids={str(r.get('event_id')) for r in decisions if r.get('decision')=='NO_TRADE' and r.get('event_id')}
    all_no_trade_ids={str(r.get('event_id')) for r in all_journal if r.get('decision')=='NO_TRADE' and r.get('event_id')}
    neutral_linked=[r for r in neutral_all if str(r.get('decision_event_id')) in no_trade_ids]
    neutral_known_outside_window=[r for r in neutral_all if str(r.get('decision_event_id')) in all_no_trade_ids and str(r.get('decision_event_id')) not in no_trade_ids]
    neutral_orphans=[r for r in neutral_all if str(r.get('decision_event_id')) not in all_no_trade_ids]
    seen_horizons=set(); complete=[]; duplicate_horizon_records=0
    for r in neutral_linked:
        key=(str(r.get('decision_event_id')), str(r.get('horizon')))
        if key in seen_horizons:
            duplicate_horizon_records += 1
            continue
        seen_horizons.add(key)
        if r.get('horizon_complete') is True: complete.append(r)
    pending_by_decision={event_id:set(('1h','4h','24h')) for event_id in no_trade_ids}
    for r in complete:
        pending_by_decision[str(r.get('decision_event_id'))].discard(r.get('horizon'))
    pending_horizons=sum(len(v) for v in pending_by_decision.values())
    outcome_classes=Counter(r.get('outcome_class','UNKNOWN') for r in complete)
    horizon_counts=Counter(r.get('horizon','UNKNOWN') for r in complete)
    # Directionless market movement is context, never counted as a trade win/loss.
    directional=[r for r in complete if r.get('directional_proposal') in ('LONG','SHORT') and r.get('hypothetical_trade_outcome')]
    candidate_rows=[]; invalid_candidate_timestamps=0
    for r in candidates_all:
        try: ts=parse_dt(r.get('observed_at'))
        except (ValueError, TypeError, OverflowError, OSError):
            invalid_candidate_timestamps += 1
            continue
        if start <= ts <= now: candidate_rows.append(r)
    candidate_gate_decisions=Counter(str(r.get('final_gate_decision','UNKNOWN')) for r in candidate_rows)
    candidate_gate_reasons=Counter()
    for row in candidate_rows:
        gate_reason_list=row.get('final_gate_reasons') or []
        if isinstance(gate_reason_list,str): gate_reason_list=[x for x in gate_reason_list.split('|') if x]
        for reason in gate_reason_list: candidate_gate_reasons[str(reason)]+=1
    paper_outcomes=[]
    # Prefer actual append-only journal outcome events for the 24h window; evaluator
    # summary rows may carry candidate timestamps rather than closure timestamps.
    for ts,r in journal:
        if r.get('decision') == 'PAPER_OUTCOME': paper_outcomes.append(r)
    if not paper_outcomes:
        for r in outcomes_all:
            try: ts=parse_dt(r.get('closed_at') or r.get('exit_time') or r.get('observed_at'))
            except Exception: continue
            if start <= ts <= now: paper_outcomes.append(r)
    # Outcome close-time window and candidate decision-time window are different cohorts.
    # Link outcomes to the full candidate ledger; never imply a closed outcome belongs to
    # a candidate generated in this same 24-hour window unless that link is verified.
    all_candidate_by_id={}
    all_candidate_by_time={}
    for c in candidates_all:
        cid=str(c.get('candidate_event_id') or c.get('event_id') or
                (f"hes-v2-candidate-{c.get('symbol','BTC_USDT')}-15m-{c.get('candidate_time')}"
                 if c.get('candidate_time') is not None else ""))
        if cid: all_candidate_by_id[cid]=c
        if c.get('candidate_time') is not None:
            all_candidate_by_time.setdefault(str(c.get('candidate_time')),[]).append(c)
    outcome_links=[]; unmatched_paper_outcomes=0; ambiguous_paper_outcomes=0
    for outcome in paper_outcomes:
        cid=str(outcome.get('candidate_event_id') or '')
        candidate=all_candidate_by_id.get(cid) if cid else None
        if candidate is None and not cid and outcome.get('candidate_time') is not None:
            choices=all_candidate_by_time.get(str(outcome.get('candidate_time')),[])
            if len(choices)==1: candidate=choices[0]
            elif len(choices)>1: ambiguous_paper_outcomes+=1
        if candidate is None:
            unmatched_paper_outcomes+=1
        else:
            outcome_links.append((outcome,candidate))
    candidate_window_ids={str(c.get('candidate_event_id') or c.get('event_id') or
        (f"hes-v2-candidate-{c.get('symbol','BTC_USDT')}-15m-{c.get('candidate_time')}"
         if c.get('candidate_time') is not None else '')) for c in candidate_rows}
    outcome_gate_decisions=Counter(str(c.get('final_gate_decision','UNKNOWN')) for _,c in outcome_links)
    outcomes_with_candidate_in_window=sum(
        1 for _,c in outcome_links
        if str(c.get('candidate_event_id') or c.get('event_id') or
           (f"hes-v2-candidate-{c.get('symbol','BTC_USDT')}-15m-{c.get('candidate_time')}"
            if c.get('candidate_time') is not None else '')) in candidate_window_ids)
    try:
        matured_validation=build_matured_validation(now)
    except Exception as exc:
        matured_validation={'status':'ERROR_FAIL_CLOSED','error':type(exc).__name__+':'+str(exc)[:180],
            'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False}
    report={
      'schema':'hes_decision_report_24h_v1','generated_at':now.isoformat(),'window_start':start.isoformat(),'window_end':now.isoformat(),'window_hours':24,
      'window_basis':'Decision/candidate events use observed_at in [window_start, window_end]. PAPER_OUTCOME events use their closure/observed_at in the same window and may refer to candidates from earlier windows; candidate linkage is reported separately.',
      'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m',
      'journal_records_total':len(all_journal),'journal_records_in_window':len(journal),'invalid_timestamp_records_excluded':invalid_timestamps,
      'candidate_records_total':len(candidates_all),'invalid_candidate_timestamps_excluded':invalid_candidate_timestamps,
      'decision_counts':dict(counts),'decision_count_total':len(decisions),'no_trade_reasons':dict(reasons),
      'matured_no_trade_validation':matured_validation,
      'no_trade_decisions_in_window':sum(r.get('decision')=='NO_TRADE' for r in decisions),
      'neutral_followup':{'outcome_horizon_records_complete':len(complete),'complete_outcome_class_counts':dict(outcome_classes),'complete_by_horizon':dict(horizon_counts),'pending_horizons':pending_horizons,'unique_no_trade_events_linked':len(no_trade_ids),'duplicate_horizon_records_ignored':duplicate_horizon_records,'followups_not_linked_to_window_no_trade_events':len(neutral_all)-len(neutral_linked),'followups_linked_to_window_no_trade_events':len(neutral_linked),'followups_known_but_outside_current_window':len(neutral_known_outside_window),'orphan_followup_records':len(neutral_orphans),'unique_orphan_followup_event_ids':len({str(r.get('decision_event_id')) for r in neutral_orphans}),'directional_hypothetical_outcomes':len(directional),'directionless_context_records':sum(r.get('outcome_class')=='DIRECTIONLESS_MARKET_CONTEXT' for r in complete),'cost_model':'UNCONFIGURED; net P&L not claimed','interpretation':'Raw per-horizon tracker classes include directionless context and proposals that may have failed decision-time gates; use matured_no_trade_validation for gate-qualified attribution, not raw class counts.'},
      'paper_evaluation':{'candidate_records_in_window':len(candidate_rows),'candidate_gate_decisions':dict(candidate_gate_decisions),'gate_approved_candidates':sum(r.get('final_gate_decision') in ('LONG','SHORT') for r in candidate_rows),'gate_rejected_candidates':sum(r.get('final_gate_decision') not in ('LONG','SHORT') for r in candidate_rows),'candidate_gate_reasons':dict(candidate_gate_reasons),'outcome_records_closed_in_window':len(paper_outcomes),'outcome_counts':dict(Counter(str(r.get('outcome','UNKNOWN')).upper() for r in paper_outcomes)),'outcome_linked_to_candidate_count':len(outcome_links),'outcomes_with_candidate_in_window_count':outcomes_with_candidate_in_window,'outcomes_linked_to_older_candidate_count':len(outcome_links)-outcomes_with_candidate_in_window,'outcome_unmatched_candidate_count':unmatched_paper_outcomes,'ambiguous_legacy_outcome_candidate_links':ambiguous_paper_outcomes,'outcome_candidate_gate_decisions':dict(outcome_gate_decisions),'note':'Paper outcomes are filtered by closure time and can refer to earlier candidate events. Stable IDs are preferred; legacy timestamp linkage is accepted only when unique. Do not mix these outcomes with NO_TRADE market-context observations.'},
      'evidence_sha256':{'journal':sha(JOURNAL),'neutral_outcomes':sha(NEUTRAL),'candidates':sha(CANDIDATES),'paper_outcomes':sha(OUTCOMES)},
      'limitations':['matured_no_trade_validation is an independent 24-48h cohort and may contain fewer decisions than the rolling 24h decision window','NO_TRADE outcomes are counterfactual observations, not proof of causality','Directionless context is not a hypothetical trade','A same-candle stop/target hit is ambiguous','NO_TRADE context records are not cost-adjusted trades; separate paper outcomes use explicit assumption-based costs','Missing or malformed timestamps are excluded and counted','No automatic policy changes'],
      'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False
    }
    # Atomic replacement prevents readers from observing a partially written report.
    tmp_report=REPORT.with_suffix(REPORT.suffix+'.tmp')
    tmp_report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp_report.replace(REPORT)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--json',action='store_true'); args=ap.parse_args()
    result=build_report()
    if args.json: print(json.dumps(result,indent=2,sort_keys=True))
    else:
      print(f"HES 24h Decision Report | {result['window_start']} -> {result['window_end']}")
      print('Decisions:',json.dumps(result['decision_counts'],sort_keys=True))
      print('NO_TRADE follow-up:',json.dumps(result['neutral_followup'],sort_keys=True))
      print('Paper evaluation:',json.dumps(result['paper_evaluation'],sort_keys=True))
      print('Safety: execution_enabled=False; orders_placed=False')
