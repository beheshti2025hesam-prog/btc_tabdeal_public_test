import importlib.util, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
MODULE=Path('/opt/hes-trade-agent/scripts/run_no_trade_decision_audit_v1.py')
spec=importlib.util.spec_from_file_location('no_trade_decision_audit_v1',MODULE)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def setup(tmp_path,monkeypatch):
 d=tmp_path/'data'/'forward'; d.mkdir(parents=True)
 for name in ('JOURNAL','NEUTRAL','CANDLES','REPORT','RECORDS'): monkeypatch.setattr(mod,name,d/({'JOURNAL':'trade_journal_v2.jsonl','NEUTRAL':'neutral_decision_outcomes_v1.jsonl','CANDLES':'candles.jsonl','REPORT':'audit.json','RECORDS':'audit.jsonl'}[name]))
 return d
def test_per_decision_review_flags_large_move_without_calling_it_missed_trade(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 rows=[{'event_id':'e1','observed_at':(now-timedelta(hours=3)).isoformat(),'decision':'NO_TRADE','direction':'NONE'}, {'event_id':'e2','observed_at':(now-timedelta(hours=2)).isoformat(),'decision':'NO_TRADE','direction':'NONE'}]
 mod.JOURNAL.write_text(''.join(json.dumps(x)+'\n' for x in rows))
 neutral=[{'decision_event_id':'e1','horizon':'1h','horizon_complete':True,'close_change_pct':1.4,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'}, {'decision_event_id':'e2','horizon':'1h','horizon_complete':True,'close_change_pct':-0.2,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'}]
 mod.NEUTRAL.write_text(''.join(json.dumps(x)+'\n' for x in neutral))
 report=mod.build_audit(now); records=[json.loads(x) for x in mod.RECORDS.read_text().splitlines()]
 assert report['unique_no_trade_decisions']==2
 assert report['screen_status_counts']=={'LARGE_MOVE_REVIEW_ONLY':1,'NO_LARGE_CLOSE_MOVE_SCREENED':1}
 assert records[0]['screen_status']=='LARGE_MOVE_REVIEW_ONLY'
 assert 'not a missed trade or avoided loss' in records[0]['interpretation']
 assert 'gate-qualified matured validation' in records[0]['interpretation']
 assert report['orders_placed'] is False and report['policy_mutation_enabled'] is False

def test_duplicate_followups_are_ignored_and_directional_outcome_is_separate(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e','observed_at':now.isoformat(),'decision':'NO_TRADE'})+'\n')
 xs=[{'decision_event_id':'e','horizon':'1h','horizon_complete':True,'close_change_pct':0.5,'directional_proposal':'SHORT','hypothetical_trade_outcome':'STOP_LOSS','outcome_class':'STOP_LOSS'}, {'decision_event_id':'e','horizon':'1h','horizon_complete':True,'close_change_pct':-2,'directional_proposal':'SHORT','hypothetical_trade_outcome':'TAKE_PROFIT','outcome_class':'TAKE_PROFIT'}]
 mod.NEUTRAL.write_text(''.join(json.dumps(x)+'\n' for x in xs))
 report=mod.build_audit(now); rec=json.loads(mod.RECORDS.read_text().splitlines()[0])
 assert report['duplicate_followups_ignored']==1
 assert rec['screen_status']=='DIRECTIONAL_COUNTERFACTUAL_AVAILABLE'
 assert rec['directional_counterfactuals_by_horizon']=={'1h':'STOP_LOSS'}

def test_malformed_json_preserves_prior_outputs(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); mod.REPORT.write_text('{"keep":true}\n'); mod.RECORDS.write_text('prior\n'); mod.JOURNAL.write_text('{broken}\n')
 with pytest.raises(ValueError,match='MALFORMED_JSONL'): mod.build_audit(datetime(2026,10,27,tzinfo=timezone.utc))
 assert json.loads(mod.REPORT.read_text())=={'keep':True}; assert mod.RECORDS.read_text()=='prior\n'


def test_gate_evidence_is_preserved_for_attribution_not_causality(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 row={'event_id':'gate-event','observed_at':now.isoformat(),'decision':'NO_TRADE','direction':'NONE','gate_evidence':{'confirmation':{'state':'UNCONFIRMED','reason_codes':['REQUIRED_CHECK_FAILED'],'passed_count':1,'required_count':3},'risk':{'state':'RISK_REJECTED','reason_codes':['NO_POLICY_CONFIGURED']},'structure':{'regime':'DOWNTREND','events':['BOS_BEARISH']}}}
 mod.JOURNAL.write_text(json.dumps(row)+'\n'); mod.NEUTRAL.write_text('')
 report=mod.build_audit(now); rec=json.loads(mod.RECORDS.read_text().splitlines()[0])
 assert rec['structure_regime']=='DOWNTREND' and rec['structure_events']==['BOS_BEARISH']
 assert rec['gate_snapshot']['confirmation']['reason_codes']==['REQUIRED_CHECK_FAILED']
 assert report['gate_state_counts']=={'confirmation:UNCONFIRMED':1,'risk:RISK_REJECTED':1}
 assert report['gate_reason_code_counts']=={'REQUIRED_CHECK_FAILED':1,'NO_POLICY_CONFIGURED':1}


def test_independent_ohlc_audit_detects_intrahorizon_extremes_with_complete_candles(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=1)
 mod.JOURNAL.write_text(json.dumps({'event_id':'ohlc','observed_at':decision.isoformat(),'decision':'NO_TRADE','direction':'NONE'})+'\n')
 mod.NEUTRAL.write_text(json.dumps({'decision_event_id':'ohlc','horizon':'1h','horizon_complete':True,'baseline_close':100.0,'close_change_pct':0.2,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'})+'\n')
 candles=[]
 for i,(hi,lo,cl) in enumerate([(100.2,99.8,100.1),(100.5,99.7,100.2),(101.8,99.5,100.3),(100.6,99.6,100.2)],1):
  close_time=int(decision.timestamp())+i*900
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'close_time':close_time,'high':str(hi),'low':str(lo),'close':str(cl)})
 mod.CANDLES.write_text(''.join(json.dumps(x)+'\n' for x in candles))
 report=mod.build_audit(now); rec=json.loads(mod.RECORDS.read_text().splitlines()[0]); metric=rec['independent_ohlc_forward_audit']['1h']
 assert metric['complete_gap_free'] is True and metric['observed_candles']==4
 assert metric['max_high_excursion_pct']==1.8 and metric['max_low_excursion_pct']==-0.5
 assert rec['screen_status']=='LARGE_MOVE_REVIEW_ONLY'
 assert report['ohlc_candle_quality_counts']['1h:COMPLETE']==1

def test_ohlc_audit_does_not_mark_gapped_candles_complete(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=1)
 mod.JOURNAL.write_text(json.dumps({'event_id':'gap','observed_at':decision.isoformat(),'decision':'NO_TRADE'})+'\n')
 mod.NEUTRAL.write_text(json.dumps({'decision_event_id':'gap','horizon':'1h','horizon_complete':True,'baseline_close':100.0,'close_change_pct':0.1})+'\n')
 candles=[]
 for i in (1,2,4):
  close_time=int(decision.timestamp())+i*900
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'close_time':close_time,'high':'101','low':'99','close':'100'})
 mod.CANDLES.write_text(''.join(json.dumps(x)+'\n' for x in candles))
 mod.build_audit(now); rec=json.loads(mod.RECORDS.read_text().splitlines()[0])
 metric=rec['independent_ohlc_forward_audit']['1h']
 assert metric['complete_gap_free'] is False and metric['observed_candles']==3
 assert 'max_high_excursion_pct' not in metric


def test_candle_feed_freshness_is_reported_and_stale_data_is_not_called_fresh(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 mod.JOURNAL.write_text('') ; mod.NEUTRAL.write_text('')
 candle={'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'close_time':int((now-timedelta(hours=1)).timestamp()),'high':'101','low':'99','close':'100'}
 mod.CANDLES.write_text(json.dumps(candle)+'\n')
 report=mod.build_audit(now)
 assert report['candle_feed_freshness']['status']=='STALE'
 assert report['candle_feed_freshness']['age_seconds']==3600
 candle['close_time']=int((now-timedelta(minutes=15)).timestamp())
 mod.CANDLES.write_text(json.dumps(candle)+'\n')
 report=mod.build_audit(now)
 assert report['candle_feed_freshness']['status']=='FRESH'
 assert report['candle_feed_freshness']['age_seconds']==900


def test_followup_linkage_distinguishes_old_known_decisions_from_true_orphans(tmp_path,monkeypatch):
 import json
 setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 rows=[
  {'event_id':'old','observed_at':(now-timedelta(hours=25)).isoformat(),'decision':'NO_TRADE'},
  {'event_id':'current','observed_at':now.isoformat(),'decision':'NO_TRADE'},
 ]
 mod.JOURNAL.write_text(''.join(json.dumps(x)+'\n' for x in rows))
 xs=[
  {'decision_event_id':'current','horizon':'1h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'},
  {'decision_event_id':'old','horizon':'24h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'},
  {'decision_event_id':'ghost','horizon':'4h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'},
 ]
 mod.NEUTRAL.write_text(''.join(json.dumps(x)+'\n' for x in xs))
 report=mod.build_audit(now)
 assert report['followups_linked_to_window_no_trade_events']==1
 assert report['followups_known_but_outside_current_window']==1
 assert report['orphan_followup_records']==1
 assert report['unique_orphan_followup_event_ids']==1


def test_audit_uses_frozen_proposal_geometry_when_final_decision_is_directionless(tmp_path,monkeypatch):
    import json
    setup(tmp_path,monkeypatch); now=datetime(2026,10,29,12,tzinfo=timezone.utc)
    row={'event_id':'proposal','observed_at':now.isoformat(),'decision':'NO_TRADE','direction':'NONE',
         'proposal_direction':'SHORT','proposal_entry':100.0,'proposal_stop_loss':102.0,'proposal_take_profit':96.0}
    mod.JOURNAL.write_text(json.dumps(row)+'\n')
    neutral={'decision_event_id':'proposal','horizon':'1h','horizon_complete':True,'close_change_pct':-1.0,
             'directional_proposal':'SHORT','entry':100.0,'stop_loss':102.0,'take_profit':96.0,
             'hypothetical_trade_outcome':'TAKE_PROFIT','outcome_class':'TAKE_PROFIT'}
    mod.NEUTRAL.write_text(json.dumps(neutral)+'\n')
    mod.build_audit(now); rec=json.loads(mod.RECORDS.read_text().splitlines()[0])
    assert rec['direction']=='NONE'  # final decision remains NO_TRADE/directionless
    assert rec['proposal_direction']=='SHORT'
    assert rec['proposal_entry']==100.0 and rec['proposal_stop_loss']==102.0 and rec['proposal_take_profit']==96.0
    assert rec['candidate_geometry_available'] is True
    assert rec['screen_status']=='DIRECTIONAL_COUNTERFACTUAL_AVAILABLE'
