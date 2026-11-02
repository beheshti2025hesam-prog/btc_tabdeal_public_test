import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[2]
MODULE=REPO_ROOT/'scripts'/'run_decision_report_24h_v1.py'
spec=importlib.util.spec_from_file_location('decision_report_24h_v1', MODULE)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_report_is_strict_rolling_window_and_safe(tmp_path, monkeypatch):
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    data=tmp_path/'data'/'forward'; data.mkdir(parents=True)
    monkeypatch.setattr(mod,'DATA',data); monkeypatch.setattr(mod,'JOURNAL',data/'trade_journal_v2.jsonl')
    monkeypatch.setattr(mod,'NEUTRAL',data/'neutral_decision_outcomes_v1.jsonl'); monkeypatch.setattr(mod,'CANDIDATES',data/'strategy_policy_v2_eval_candidates.jsonl')
    monkeypatch.setattr(mod,'OUTCOMES',data/'strategy_policy_v2_eval_outcomes.jsonl'); monkeypatch.setattr(mod,'REPORT',data/'report.json')
    rows=[{'event_id':'old','observed_at':(now-timedelta(hours=25)).isoformat(),'decision':'NO_TRADE'},
          {'event_id':'new','observed_at':(now-timedelta(hours=2)).isoformat(),'decision':'NO_TRADE','no_trade_reason':'GATE_A|GATE_B'},
          {'event_id':'paper','observed_at':(now-timedelta(hours=1)).isoformat(),'decision':'PAPER_CANDIDATE'}]
    mod.JOURNAL.write_text(''.join(__import__('json').dumps(x)+'\n' for x in rows))
    mod.NEUTRAL.write_text(__import__('json').dumps({'decision_event_id':'new','horizon':'1h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'})+'\n')
    (data/'strategy_policy_v2_eval_candidates.jsonl').write_text(__import__('json').dumps({'observed_at':(now-timedelta(hours=1)).isoformat(),'final_gate_decision':'NO_TRADE','final_gate_reasons':['GATE_X','GATE_Y']})+'\n')
    report=mod.build_report(now)
    assert report['decision_counts']=={'NO_TRADE':1}
    assert report['no_trade_reasons']=={'GATE_A':1,'GATE_B':1}
    assert report['neutral_followup']['directionless_context_records']==1
    assert report['matured_no_trade_validation']['status']=='OK'
    assert 'Raw per-horizon tracker classes' in report['neutral_followup']['interpretation']
    assert report['matured_no_trade_validation']['decision_quality_methodology']['cost_model'].startswith('UNCONFIGURED')
    assert 'rejected_proposal_counterfactuals' in report['matured_no_trade_validation']
    assert report['matured_no_trade_validation']['execution_enabled'] is False
    assert report['matured_no_trade_validation']['decisions_in_matured_cohort']==1
    assert report['paper_evaluation']['candidate_gate_decisions']=={'NO_TRADE':1}
    assert report['paper_evaluation']['candidate_gate_reasons']=={'GATE_X':1,'GATE_Y':1}
    assert report['policy_mutation_enabled'] is False and report['execution_enabled'] is False and report['orders_placed'] is False


def _isolate_report_paths(tmp_path, monkeypatch):
    import json
    data=tmp_path/'data'/'forward'; data.mkdir(parents=True)
    monkeypatch.setattr(mod,'DATA',data); monkeypatch.setattr(mod,'JOURNAL',data/'trade_journal_v2.jsonl')
    monkeypatch.setattr(mod,'NEUTRAL',data/'neutral_decision_outcomes_v1.jsonl')
    monkeypatch.setattr(mod,'CANDIDATES',data/'strategy_policy_v2_eval_candidates.jsonl')
    monkeypatch.setattr(mod,'OUTCOMES',data/'strategy_policy_v2_eval_outcomes.jsonl')
    monkeypatch.setattr(mod,'REPORT',data/'report.json')
    return data


def test_naive_timestamps_are_utc_and_window_boundaries_are_inclusive(tmp_path, monkeypatch):
    import json
    data=_isolate_report_paths(tmp_path,monkeypatch)
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    rows=[{'event_id':'at_start','observed_at':'2026-10-26T12:00:00','decision':'NO_TRADE'},
          {'event_id':'at_end','observed_at':'2026-10-27T12:00:00Z','decision':'SHORT'},
          {'event_id':'too_old','observed_at':'2026-10-26T11:59:59Z','decision':'LONG'},
          {'event_id':'bad_ts','observed_at':'not-a-time','decision':'NO_TRADE'}]
    mod.JOURNAL.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    report=mod.build_report(now)
    assert report['decision_counts']=={'NO_TRADE':1,'SHORT':1}
    assert report['invalid_timestamp_records_excluded']==1
    assert mod.parse_dt('2026-10-27T12:00:00').tzinfo==timezone.utc


def test_followups_link_only_to_unique_no_trade_ids_and_dedupe_horizons(tmp_path, monkeypatch):
    import json
    data=_isolate_report_paths(tmp_path,monkeypatch)
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    rows=[{'event_id':'old','observed_at':(now-timedelta(hours=25)).isoformat(),'decision':'NO_TRADE'},
          {'event_id':'nt1','observed_at':(now-timedelta(hours=1)).isoformat(),'decision':'NO_TRADE'},
          {'event_id':'nt1','observed_at':(now-timedelta(minutes=59)).isoformat(),'decision':'NO_TRADE'},
          {'event_id':'long1','observed_at':(now-timedelta(minutes=30)).isoformat(),'decision':'LONG'}]
    mod.JOURNAL.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    followups=[{'decision_event_id':'nt1','horizon':'1h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'},
               {'decision_event_id':'nt1','horizon':'1h','horizon_complete':True,'outcome_class':'STOP_LOSS'},
               {'decision_event_id':'old','horizon':'24h','horizon_complete':True,'outcome_class':'DIRECTIONLESS_MARKET_CONTEXT'},
               {'decision_event_id':'long1','horizon':'4h','horizon_complete':True,'outcome_class':'STOP_LOSS'},
               {'decision_event_id':'orphan','horizon':'24h','horizon_complete':True,'outcome_class':'STOP_LOSS'}]
    mod.NEUTRAL.write_text(''.join(json.dumps(x)+'\n' for x in followups))
    report=mod.build_report(now)
    neutral=report['neutral_followup']
    assert neutral['unique_no_trade_events_linked']==1
    assert neutral['outcome_horizon_records_complete']==1
    assert neutral['complete_outcome_class_counts']=={'DIRECTIONLESS_MARKET_CONTEXT':1}
    assert neutral['pending_horizons']==2
    assert neutral['duplicate_horizon_records_ignored']==1
    assert neutral['followups_not_linked_to_window_no_trade_events']==3
    assert neutral['followups_known_but_outside_current_window']==1
    assert neutral['orphan_followup_records']==2


def test_invalid_candidate_timestamp_is_counted_and_report_replaced_atomically(tmp_path, monkeypatch):
    import json
    data=_isolate_report_paths(tmp_path,monkeypatch)
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    mod.JOURNAL.write_text(json.dumps({'event_id':'x','observed_at':now.isoformat(),'decision':'NO_TRADE'})+'\n')
    mod.CANDIDATES.write_text(json.dumps({'observed_at':'broken','final_gate_decision':'LONG'})+'\n')
    report=mod.build_report(now)
    assert report['invalid_candidate_timestamps_excluded']==1
    assert report['candidate_records_total']==1
    assert (data/'report.json').exists()
    assert not (data/'report.json.tmp').exists()


def test_malformed_jsonl_fails_closed_without_overwriting_existing_report(tmp_path, monkeypatch):
    import json, pytest
    data=_isolate_report_paths(tmp_path,monkeypatch)
    mod.REPORT.write_text('{"sentinel":"keep"}\n')
    mod.JOURNAL.write_text('{broken json}\n')
    with pytest.raises(ValueError, match='MALFORMED_JSONL'):
        mod.build_report(datetime(2026,10,27,12,0,tzinfo=timezone.utc))
    assert json.loads(mod.REPORT.read_text())=={'sentinel':'keep'}


def test_closed_paper_outcome_is_linked_to_older_candidate_without_mislabeling_window(tmp_path, monkeypatch):
    import json
    data=_isolate_report_paths(tmp_path,monkeypatch)
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    candidate={'event_id':'cand-old','candidate_event_id':'cand-old','candidate_time':100,
               'observed_at':(now-timedelta(hours=25)).isoformat(),'decision':'PAPER_CANDIDATE',
               'direction':'SHORT','final_gate_decision':'NO_TRADE','entry':100,'stop_loss':101,'take_profit':97}
    outcome={'event_id':'out-1','candidate_event_id':'cand-old','candidate_time':100,
             'observed_at':now.isoformat(),'decision':'PAPER_OUTCOME','outcome':'losses','direction':'SHORT'}
    mod.JOURNAL.write_text(''.join(json.dumps(x)+'\n' for x in [candidate,outcome]))
    mod.CANDIDATES.write_text(json.dumps(candidate)+'\n')
    report=mod.build_report(now)
    paper=report['paper_evaluation']
    assert paper['candidate_records_in_window']==0
    assert paper['outcome_records_closed_in_window']==1
    assert paper['outcome_linked_to_candidate_count']==1
    assert paper['outcomes_with_candidate_in_window_count']==0
    assert paper['outcomes_linked_to_older_candidate_count']==1
    assert paper['outcome_candidate_gate_decisions']=={'NO_TRADE':1}
    assert paper['outcome_unmatched_candidate_count']==0
    assert 'may refer to candidates from earlier windows' in report['window_basis']


def test_report_script_path_is_resolved_from_repository_root():
    expected = Path(__file__).resolve().parents[2] / "scripts" / "run_decision_report_24h_v1.py"
    assert MODULE == expected
    assert MODULE.is_file()
