import importlib.util,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
REPO_ROOT=Path(__file__).resolve().parents[2]
MODULE=REPO_ROOT/'scripts'/'run_matured_no_trade_validation_v1.py'
spec=importlib.util.spec_from_file_location('matured_no_trade_validation_v1',MODULE); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def setup(tmp_path,monkeypatch):
 d=tmp_path/'data'/'forward'; d.mkdir(parents=True)
 for name,file in [('JOURNAL','journal.jsonl'),('CANDLES','candles.jsonl'),('NEUTRAL','neutral.jsonl'),('REPORT','report.json'),('RECORDS','records.jsonl')]: monkeypatch.setattr(mod,name,d/file)
 return d
def test_matured_cohort_requires_complete_gap_free_horizons_and_crosschecks_tracker(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e1','observed_at':decision.isoformat(),'decision':'NO_TRADE','direction':'NONE','gate_reasons':['UNCONFIRMED']})+'\n')
 candles=[]
 base=int(decision.timestamp())//900*900
 # Align the decision 1 second after a candle close; then 96 continuous post-decision closes fit within 24h.
 decision= datetime.fromtimestamp(base+1,timezone.utc)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e1','observed_at':decision.isoformat(),'decision':'NO_TRADE','direction':'NONE','gate_reasons':['UNCONFIRMED']})+'\n')
 for i in range(-1,97):
  ct=base+(i+1)*900; op=ct-900; close=100+i*.01
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'open_time':op,'close_time':ct,'open':str(close),'high':str(close+1),'low':str(close-1),'close':str(close),'volume':'10'})
 mod.CANDLES.write_text(''.join(json.dumps(c)+'\n' for c in candles))
 tracker={'decision_event_id':'e1','horizon':'24h','horizon_complete':True,'baseline_close':100.0,'last_close':100.96,'close_change_pct':0.96}
 mod.NEUTRAL.write_text(json.dumps(tracker)+'\n')
 report=mod.build(now); row=json.loads(mod.RECORDS.read_text().splitlines()[0])
 assert report['decisions_in_matured_cohort']==1
 assert row['horizons']['24h']['gap_free_complete'] is True
 # The decision occurred one second after the prior close, so the exact 24h
 # boundary is crossed by the 97th subsequent close; metrics must use that same
 # boundary candle as the append-only outcome tracker.
 assert row['horizons']['24h']['observed_candles']==97
 assert row['horizons']['24h']['last_close']==100.96
 assert report['complete_gap_free_24h_decisions']==1
 assert report['tracker_boundary_comparisons']==1 and report['tracker_boundary_mismatches']==0
 assert report['execution_enabled'] is False and report['orders_placed'] is False

def test_matured_cohort_rejects_missing_candle_coverage(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e1','observed_at':decision.isoformat(),'decision':'NO_TRADE'})+'\n')
 mod.CANDLES.write_text(''); mod.NEUTRAL.write_text('')
 report=mod.build(now)
 assert report['decisions_in_matured_cohort']==1
 assert report['complete_gap_free_24h_decisions']==0
 assert report['validation_status_counts']=={'INCOMPLETE_FORWARD_COVERAGE':1}

def test_malformed_input_preserves_previous_reports(tmp_path,monkeypatch):
 setup(tmp_path,monkeypatch); mod.JOURNAL.write_text('{broken}\n'); mod.REPORT.write_text('{"old":true}\n'); mod.RECORDS.write_text('prior\n')
 with pytest.raises(ValueError,match='MALFORMED_JSONL'): mod.build(datetime(2026,10,27,tzinfo=timezone.utc))
 assert json.loads(mod.REPORT.read_text())=={'old':True} and mod.RECORDS.read_text()=='prior\n'

def test_directional_counterfactuals_are_separate_from_directionless_context(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e1','observed_at':decision.isoformat(),'decision':'NO_TRADE','direction':'NONE','proposal_direction':'SHORT','gate_reasons':[],'gate_evidence':{'confirmation':{'state':'CONFIRMED_SHORT','checks':[{'state':'PASS'}]},'risk':{'state':'RISK_APPROVED','checks':[{'state':'PASS'}]},'structure':{'status':'OBSERVED','regime':'DOWNTREND'}}})+'\n')
 base=int(decision.timestamp())//900*900
 candles=[]
 for i in range(-1,97):
  ct=base+(i+1)*900; close=100+i*.01
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'open_time':ct-900,'close_time':ct,'open':str(close),'high':str(close+1),'low':str(close-1),'close':str(close),'volume':'10'})
 mod.CANDLES.write_text(''.join(json.dumps(c)+'\n' for c in candles))
 rows=[]
 for h,cls in [('1h','TIMEOUT_NEGATIVE'),('4h','STOP_LOSS'),('24h','STOP_LOSS')]:
  rows.append({'decision_event_id':'e1','horizon':h,'horizon_complete':True,'directional_proposal':'SHORT','entry':100.0,'stop_loss':101.0,'take_profit':97.0,'outcome_class':cls,'baseline_close':100.0,'last_close':101.0,'close_change_pct':1.0})
 mod.NEUTRAL.write_text(''.join(json.dumps(r)+'\n' for r in rows))
 report=mod.build(now)
 assert report['directional_counterfactuals']['evaluated_unique_decisions']==1
 assert report['directional_counterfactuals']['decisions_with_any_negative_hypothetical_outcome']==1
 assert report['directional_counterfactuals']['outcome_class_counts_by_horizon']['4h']=={'STOP_LOSS':1}
 assert report['policy_mutation_enabled'] is False and report['orders_placed'] is False

def test_quality_buckets_do_not_call_directionless_move_a_missed_trade(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 mod.JOURNAL.write_text(json.dumps({'event_id':'e2','observed_at':decision.isoformat(),'decision':'NO_TRADE','direction':'NONE','gate_reasons':['NO_VALID_CANDIDATE']})+'\n')
 base=int(decision.timestamp())//900*900; candles=[]
 for i in range(-1,97):
  ct=base+(i+1)*900; close=100+i*.02
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,'open_time':ct-900,'close_time':ct,'open':str(close),'high':str(close+1),'low':str(close-1),'volume':'10'})
 mod.CANDLES.write_text(''.join(json.dumps(c)+'\n' for c in candles))
 mod.NEUTRAL.write_text(''.join(json.dumps({'decision_event_id':'e2','horizon':h,'horizon_complete':True,'directional_proposal':'NONE','outcome_class':'DIRECTIONLESS_MARKET_CONTEXT','close_change_pct':1.0,'max_favorable_excursion_pct':2.0,'max_adverse_excursion_pct':-1.0})+'\n' for h in ('1h','4h','24h')))
 report=mod.build(now); b=report['decision_quality_buckets_by_horizon']['24h']
 assert b['matured_decisions']==1 and b['unclassifiable_no_valid_setup']==1
 assert b['large_move_context_only']==1 and b['missed_profit_hypotheses']==0 and b['avoided_loss_hypotheses']==0


def test_gate_rejected_profitable_proposal_is_not_a_missed_profit(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 journal={'event_id':'rejected','observed_at':decision.isoformat(),'decision':'NO_TRADE',
          'direction':'NONE','proposal_direction':'SHORT','proposal_entry':100.0,
          'proposal_stop_loss':101.0,'proposal_take_profit':97.0,
          'gate_reasons':['MARKET_STRUCTURE_UNKNOWN_OR_INSUFFICIENT','NO_VALID_CANDIDATE','CONFIRMATION_NOT_VALID'],
          'gate_evidence':{'confirmation':{'state':'UNCONFIRMED','checks':[{'state':'FAIL'}]},
                           'risk':{'state':'RISK_REJECTED','checks':[{'state':'FAIL'}]},
                           'structure':{'status':'OBSERVED','regime':'UNKNOWN'}}}
 mod.JOURNAL.write_text(json.dumps(journal)+'\n')
 base=int(decision.timestamp())//900*900; candles=[]
 for i in range(-1,97):
  ct=base+(i+1)*900; close=100.0
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,
                  'open_time':ct-900,'close_time':ct,'open':str(close),'high':'100.5','low':'96.5',
                  'close':str(close),'volume':'10'})
 mod.CANDLES.write_text(''.join(json.dumps(c)+'\n' for c in candles))
 rows=[{'decision_event_id':'rejected','horizon':h,'horizon_complete':True,
        'directional_proposal':'SHORT','entry':100.0,'stop_loss':101.0,'take_profit':97.0,
        'outcome_class':'TAKE_PROFIT','baseline_close':100.0,'last_close':100.0,
        'close_change_pct':0.0} for h in ('1h','4h','24h')]
 mod.NEUTRAL.write_text(''.join(json.dumps(r)+'\n' for r in rows))
 report=mod.build(now); b=report['decision_quality_buckets_by_horizon']['24h']
 assert b['valid_directional_setup']==0
 assert b['missed_profit_hypotheses']==0 and b['avoided_loss_hypotheses']==0
 assert b['gate_rejected_proposals']==1
 assert b['rejected_proposal_missed_profit_hypotheses']==1
 assert report['directional_counterfactuals']['evaluated_unique_decisions']==0
 assert report['rejected_proposal_counterfactuals']['evaluated_unique_decisions']==1
 assert report['rejected_proposal_counterfactuals']['decisions_with_any_positive_hypothetical_outcome']==1
 assert report['policy_mutation_enabled'] is False and report['orders_placed'] is False


def test_final_policy_hold_is_reported_separately_from_missed_profit(tmp_path,monkeypatch):
 d=setup(tmp_path,monkeypatch); now=datetime(2026,10,27,12,tzinfo=timezone.utc); decision=now-timedelta(hours=30)
 journal={'event_id':'preapproval','observed_at':decision.isoformat(),'decision':'NO_TRADE',
          'direction':'NONE','proposal_direction':'SHORT','proposal_entry':100.0,
          'proposal_stop_loss':101.0,'proposal_take_profit':97.0,
          'gate_reasons':['FINAL_POLICY_APPROVAL_REQUIRED'],
          'gate_evidence':{'confirmation':{'state':'CONFIRMED_SHORT','checks':[{'state':'PASS'}]},
                           'risk':{'state':'RISK_APPROVED','checks':[{'state':'PASS'}]},
                           'structure':{'status':'OBSERVED','regime':'DOWNTREND'}}}
 mod.JOURNAL.write_text(json.dumps(journal)+'\n')
 base=int(decision.timestamp())//900*900; candles=[]
 for i in range(-1,97):
  ct=base+(i+1)*900
  candles.append({'source':'gateio_public_spot','symbol':'BTC_USDT','timeframe':'15m','closed':True,
                  'open_time':ct-900,'close_time':ct,'open':'100','high':'100.5','low':'96.5',
                  'close':'100','volume':'10'})
 mod.CANDLES.write_text(''.join(json.dumps(c)+'\n' for c in candles))
 rows=[{'decision_event_id':'preapproval','horizon':h,'horizon_complete':True,
        'directional_proposal':'SHORT','entry':100.0,'stop_loss':101.0,'take_profit':97.0,
        'outcome_class':'TAKE_PROFIT','baseline_close':100.0,'last_close':100.0,
        'close_change_pct':0.0} for h in ('1h','4h','24h')]
 mod.NEUTRAL.write_text(''.join(json.dumps(r)+'\n' for r in rows))
 report=mod.build(now); b=report['decision_quality_buckets_by_horizon']['24h']
 assert b['valid_directional_setup']==0 and b['missed_profit_hypotheses']==0
 assert b['preapproval_hold_directional_setup']==1
 assert b['preapproval_hold_missed_profit_hypotheses']==1
 assert report['preapproval_hold_counterfactuals']['evaluated_unique_decisions']==1
 assert report['directional_counterfactuals']['evaluated_unique_decisions']==0
 assert report['policy_mutation_enabled'] is False and report['orders_placed'] is False
