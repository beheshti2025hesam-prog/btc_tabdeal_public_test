#!/usr/bin/env python3
"""Per-decision NO_TRADE audit; screening only, never labels movement as a missed trade."""
from __future__ import annotations
import json, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
from scripts.runtime_paths_v1 import CODE_ROOT, DATA_ROOT
ROOT=DATA_ROOT; DATA=ROOT/'data/forward'
JOURNAL=DATA/'trade_journal_v2.jsonl'; NEUTRAL=DATA/'neutral_decision_outcomes_v1.jsonl'
CANDLES=DATA/'global_market_candles_v1.jsonl'
REPORT=DATA/'no_trade_decision_audit_24h_v1.json'; RECORDS=DATA/'no_trade_decision_audit_24h_v1.jsonl'
LARGE_MOVE_ABS_CLOSE_CHANGE_PCT=1.0
CANDLE_FEED_STALE_AFTER_SECONDS=1800
HORIZONS=('1h','4h','24h')
def parse_dt(v):
    if v is None or isinstance(v,bool) or v=='': raise ValueError('INVALID_TIMESTAMP')
    if isinstance(v,(int,float)): return datetime.fromtimestamp(v,timezone.utc)
    dt=v if isinstance(v,datetime) else datetime.fromisoformat(str(v).replace('Z','+00:00'))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
def read_jsonl(path):
    if not path.exists(): return []
    out=[]
    for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as e: raise ValueError(f'MALFORMED_JSONL:{path.name}:{n}') from e
        if not isinstance(row,dict): raise ValueError(f'INVALID_RECORD:{path.name}:{n}')
        out.append(row)
    return out
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def build_audit(now=None):
    now=parse_dt(now if now is not None else datetime.now(timezone.utc)); start=now-timedelta(hours=24)
    journal=read_jsonl(JOURNAL); neutral=read_jsonl(NEUTRAL); candle_rows=read_jsonl(CANDLES)
    candles=[]; invalid_candles=0
    for c in candle_rows:
        if c.get('source')!='gateio_public_spot' or c.get('symbol')!='BTC_USDT' or c.get('timeframe')!='15m' or c.get('closed') is not True: continue
        try:
            ct=int(c['close_time']); vals=[float(c[k]) for k in ('high','low','close')]
            if min(vals)<=0 or vals[0]<vals[1]: raise ValueError('BAD_OHLC')
            candles.append((ct,c))
        except (KeyError,ValueError,TypeError,OverflowError): invalid_candles+=1
    candles.sort(key=lambda item:item[0])
    latest_candle_epoch=candles[-1][0] if candles else None
    candle_age_seconds=max(0,int(now.timestamp()-latest_candle_epoch)) if latest_candle_epoch is not None else None
    candle_feed_freshness={'status':('NO_DATA' if latest_candle_epoch is None else ('STALE' if candle_age_seconds>CANDLE_FEED_STALE_AFTER_SECONDS else 'FRESH')),'last_closed_candle_at':datetime.fromtimestamp(latest_candle_epoch,timezone.utc).isoformat() if latest_candle_epoch is not None else None,'age_seconds':candle_age_seconds,'stale_after_seconds':CANDLE_FEED_STALE_AFTER_SECONDS}
    selected={}; invalid_ts=0
    all_no_trade_ids=set()
    for r in journal:
        if r.get('decision')!='NO_TRADE' or not r.get('event_id'): continue
        all_no_trade_ids.add(str(r['event_id']))
        try: ts=parse_dt(r.get('observed_at'))
        except (ValueError,TypeError,OverflowError,OSError): invalid_ts+=1; continue
        if start <= ts <= now:
            key=str(r['event_id'])
            if key not in selected or ts > selected[key][0]: selected[key]=(ts,r)
    followups=defaultdict(dict); duplicate=0; unlinked=0
    known_outside_window=0; orphan_followups=0; orphan_ids=set()
    ids=set(selected)
    for r in neutral:
        eid=str(r.get('decision_event_id',''))
        if eid not in ids:
            unlinked+=1
            if eid in all_no_trade_ids: known_outside_window+=1
            else:
                orphan_followups+=1
                orphan_ids.add(eid)
            continue
        h=str(r.get('horizon','UNKNOWN'))
        if h in followups[eid]: duplicate+=1; continue
        followups[eid][h]=r
    records=[]; status_counts=Counter(); flagged=[]; gate_state_counts=Counter(); gate_reason_counts=Counter(); regime_counts=Counter(); candle_quality_counts=Counter()
    for eid,(ts,r) in sorted(selected.items(),key=lambda kv:(kv[1][0],kv[0])):
        horizons=followups.get(eid,{})
        completed={h:x for h,x in horizons.items() if h in HORIZONS and x.get('horizon_complete') is True}
        changes={h:float(x['close_change_pct']) for h,x in completed.items() if isinstance(x.get('close_change_pct'),(int,float))}
        # Independent OHLC audit: require a complete, gap-free sequence of closed 15m candles.
        baseline=next((float(x['baseline_close']) for x in horizons.values() if isinstance(x.get('baseline_close'),(int,float)) and float(x['baseline_close'])>0),None)
        ohlc_metrics={}; ts_epoch=ts.timestamp()
        for horizon,hours in (('1h',1),('4h',4),('24h',24)):
            end_epoch=ts_epoch+hours*3600
            selected_candles=[c for ct,c in candles if ts_epoch < ct <= end_epoch]
            expected=hours*4
            closes=[int(c['close_time']) for c in selected_candles]
            complete_seq=(len(closes)==expected and all(b-a==900 for a,b in zip(closes,closes[1:])))
            metric={'expected_candles':expected,'observed_candles':len(selected_candles),'complete_gap_free':complete_seq}
            if complete_seq and baseline is not None:
                high=max(float(c['high']) for c in selected_candles); low=min(float(c['low']) for c in selected_candles); last=float(selected_candles[-1]['close'])
                metric.update({'last_close_change_pct':round((last/baseline-1)*100,6),'max_high_excursion_pct':round((high/baseline-1)*100,6),'max_low_excursion_pct':round((low/baseline-1)*100,6),'high_low_range_pct':round((high/low-1)*100,6)})
            else: metric['quality_status']='INCOMPLETE_OR_GAPPED' if not complete_seq else 'BASELINE_MISSING'
            ohlc_metrics[horizon]=metric
            candle_quality_counts[f"{horizon}:{'COMPLETE' if complete_seq and baseline is not None else 'INCOMPLETE'}"]+=1
        ohlc_changes={h:m['last_close_change_pct'] for h,m in ohlc_metrics.items() if 'last_close_change_pct' in m}
        ohlc_max_excursion=max((max(abs(m[k]) for k in ('max_high_excursion_pct','max_low_excursion_pct')) for m in ohlc_metrics.values() if 'max_high_excursion_pct' in m),default=None)
        max_abs=max((abs(v) for v in changes.values()),default=None)
        directional=[x for x in completed.values() if x.get('directional_proposal') in ('LONG','SHORT') and x.get('hypothetical_trade_outcome')]
        if directional: status='DIRECTIONAL_COUNTERFACTUAL_AVAILABLE'
        elif max_abs is None and ohlc_max_excursion is None: status='INSUFFICIENT_FORWARD_DATA'
        elif max(max_abs or 0, ohlc_max_excursion or 0) >= LARGE_MOVE_ABS_CLOSE_CHANGE_PCT: status='LARGE_MOVE_REVIEW_ONLY'
        else: status='NO_LARGE_CLOSE_MOVE_SCREENED'
        ge=r.get('gate_evidence') if isinstance(r.get('gate_evidence'),dict) else {}
        gate_snapshot={}
        for gate_name,gate_data in ge.items():
            if not isinstance(gate_data,dict): continue
            state=gate_data.get('state')
            codes=gate_data.get('reason_codes') or []
            gate_snapshot[gate_name]={'state':state,'reason_codes':codes,'passed_count':gate_data.get('passed_count'),'required_count':gate_data.get('required_count')}
            if state: gate_state_counts[f'{gate_name}:{state}']+=1
            for code in codes: gate_reason_counts[str(code)]+=1
        structure=ge.get('structure') if isinstance(ge.get('structure'),dict) else {}
        regime=str(structure.get('regime') or 'UNKNOWN'); regime_counts[regime]+=1
        # Preserve frozen proposal geometry separately from the final NO_TRADE direction.
        # A journal row can correctly have direction='NONE' while proposal_direction carries
        # the rejected LONG/SHORT proposal that the neutral tracker evaluated counterfactually.
        proposal_direction = r.get('proposal_direction') if r.get('proposal_direction') in ('LONG','SHORT') else (r.get('direction') if r.get('direction') in ('LONG','SHORT') else 'NONE')
        proposal_entry = r.get('proposal_entry') if r.get('proposal_entry') is not None else r.get('entry')
        proposal_stop = r.get('proposal_stop_loss') if r.get('proposal_stop_loss') is not None else r.get('stop_loss')
        proposal_target = r.get('proposal_take_profit') if r.get('proposal_take_profit') is not None else r.get('take_profit')
        proposal_geometry_available = False
        if proposal_direction in ('LONG','SHORT') and all(v is not None for v in (proposal_entry, proposal_stop, proposal_target)):
            try:
                pe, ps, pt = map(float, (proposal_entry, proposal_stop, proposal_target))
                proposal_geometry_available = pe > 0 and ps > 0 and pt > 0 and ((ps < pe < pt) if proposal_direction == 'LONG' else (pt < pe < ps))
            except (TypeError, ValueError):
                proposal_geometry_available = False
        raw_reasons=r.get('gate_reasons') or r.get('final_gate_reasons') or r.get('no_trade_reason') or []
        if isinstance(raw_reasons,str): raw_reasons=[x for x in raw_reasons.split('|') if x]
        rec={'schema':'hes_no_trade_decision_audit_record_v1','event_id':eid,'observed_at':ts.isoformat(),'decision':'NO_TRADE','direction':r.get('direction') or r.get('proposal_direction') or 'NONE','policy_version':r.get('policy_version'),'gate_reasons':raw_reasons,'gate_snapshot':gate_snapshot,'structure_regime':regime,'structure_events':structure.get('events') or [],'proposal_direction':proposal_direction,'proposal_entry':proposal_entry,'proposal_stop_loss':proposal_stop,'proposal_take_profit':proposal_target,'candidate_geometry_available':proposal_geometry_available,'source':r.get('evidence_source') or 'gateio_public_spot','symbol':r.get('symbol','BTC_USDT'),'timeframe':r.get('timeframe','15m'),'completed_horizons':sorted(completed),'pending_horizons':[h for h in HORIZONS if h not in completed],'close_change_pct_by_horizon':changes,'max_abs_close_change_pct':max_abs,'independent_ohlc_forward_audit':ohlc_metrics,'max_abs_ohlc_excursion_pct':ohlc_max_excursion,'screening_threshold_abs_close_change_pct':LARGE_MOVE_ABS_CLOSE_CHANGE_PCT,'screen_status':status,'outcome_classes_by_horizon':{h:x.get('outcome_class','UNKNOWN') for h,x in completed.items()},'directional_counterfactuals_by_horizon':{h:x.get('hypothetical_trade_outcome') for h,x in completed.items() if x.get('directional_proposal') in ('LONG','SHORT') and x.get('hypothetical_trade_outcome')},'interpretation':'Screen flags and directional proposal counterfactuals are review-only. A later TP/SL on a proposal rejected by decision-time confirmation/structure/risk gates is not a missed trade or avoided loss; use gate-qualified matured validation for those hypotheses. Directionless movement is not assigned a trade direction.','policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False}
        records.append(rec); status_counts[status]+=1
        if status=='LARGE_MOVE_REVIEW_ONLY': flagged.append(eid)
    out={'schema':'hes_no_trade_decision_audit_24h_v1','generated_at':now.isoformat(),'window_start':start.isoformat(),'window_end':now.isoformat(),'window_hours':24,'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','candle_feed_freshness':candle_feed_freshness,'screening_threshold_abs_close_change_pct':LARGE_MOVE_ABS_CLOSE_CHANGE_PCT,'threshold_note':'Predefined triage threshold only; not a trading rule or profitability claim.','unique_no_trade_decisions':len(records),'invalid_timestamps_excluded':invalid_ts,'duplicate_followups_ignored':duplicate,'followups_not_linked_to_window_no_trade_events':unlinked,'followups_linked_to_window_no_trade_events':len(neutral)-unlinked,'followups_known_but_outside_current_window':known_outside_window,'orphan_followup_records':orphan_followups,'unique_orphan_followup_event_ids':len(orphan_ids),'screen_status_counts':dict(status_counts),'ohlc_candle_quality_counts':dict(candle_quality_counts),'invalid_candle_records_excluded':invalid_candles,'structure_regime_counts':dict(regime_counts),'gate_state_counts':dict(gate_state_counts),'gate_reason_code_counts':dict(gate_reason_counts),'large_move_review_event_ids':flagged,'records_sha256':hashlib.sha256(('\n'.join(json.dumps(x,sort_keys=True,separators=(',',':')) for x in records)+'\n').encode()).hexdigest(),'source_sha256':{'journal':sha(JOURNAL),'neutral_outcomes':sha(NEUTRAL),'closed_market_candles':sha(CANDLES)},'limitations':['OHLC excursion is a market-context screen, not a directional trade P&L','Freshness checks do not prove that the source has no silent data gaps outside the inspected horizons','A large move is not evidence that a valid signal existed','Directional hypothetical outcomes remain counterfactual','Transaction costs are unconfigured','No policy tuning or live execution'], 'policy_mutation_enabled':False,'execution_enabled':False,'orders_placed':False}
    # Both outputs are atomically replaced; malformed input raises before touching existing files.
    tmp=RECORDS.with_suffix(RECORDS.suffix+'.tmp'); tmp.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in records),encoding='utf-8'); tmp.replace(RECORDS)
    tmp=REPORT.with_suffix(REPORT.suffix+'.tmp'); tmp.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8'); tmp.replace(REPORT)
    return out
if __name__=='__main__': print(json.dumps(build_audit(),indent=2,sort_keys=True))
