import json, importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'run_strategy_learning_loop_v1.py'
spec = importlib.util.spec_from_file_location('strategy_learning_loop_v1', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_read_jsonl_counts_and_rejects_malformed(tmp_path):
    p = tmp_path / 'evidence.jsonl'
    p.write_text(json.dumps({'decision':'NO_TRADE'}) + '\n' + '\n')
    assert mod.read_jsonl(p) == [{'decision':'NO_TRADE'}]
    p.write_text('{not-json}\n')
    try:
        mod.read_jsonl(p)
    except RuntimeError as exc:
        assert 'malformed evidence' in str(exc)
    else:
        raise AssertionError('malformed evidence must fail closed')

def test_hash_is_stable_and_missing_evidence_is_none(tmp_path):
    p = tmp_path / 'evidence.jsonl'
    assert mod.sha(p) is None
    p.write_text('{"x":1}\n')
    first = mod.sha(p)
    assert len(first) == 64 and mod.sha(p) == first

def test_learning_loop_source_is_read_only_and_hypothesis_only():
    source = SCRIPT.read_text()
    assert "'mode':'READ_ONLY_HYPOTHESIS_ONLY'" in source
    assert "'policy_mutation_enabled':False" in source
    assert "'execution_enabled':False" in source
    assert 'time.sleep(300)' in source


def test_only_gate_approved_candidates_count_as_strategy_performance():
    outcomes = [
        {'candidate_time': 100, 'outcome': 'losses'},
        {'candidate_time': 200, 'outcome': 'wins'},
        {'candidate_time': 300, 'outcome': 'timeouts'},
        {'candidate_time': 400, 'outcome': 'losses'},
    ]
    candidates = [
        {'candidate_time': 100, 'final_gate_decision': 'NO_TRADE'},
        {'candidate_time': 200, 'final_gate_decision': 'LONG'},
        {'candidate_time': 300, 'final_gate_decision': 'NO_TRADE'},
    ]
    eligible, research = mod.classify_outcomes_by_gate(outcomes, candidates)
    assert [x['candidate_time'] for x in eligible] == [200]
    assert [x['candidate_time'] for x in research] == [100, 300, 400]


def test_stable_candidate_ids_are_used_before_legacy_timestamp_fallback():
    outcomes = [
        {'candidate_event_id':'cand-A','candidate_time':100,'outcome':'wins'},
        {'candidate_event_id':'cand-B','candidate_time':100,'outcome':'losses'},
        {'candidate_time':100,'outcome':'wins'},
    ]
    candidates = [
        {'candidate_event_id':'cand-A','candidate_time':100,'final_gate_decision':'LONG'},
        {'candidate_event_id':'cand-B','candidate_time':100,'final_gate_decision':'NO_TRADE'},
    ]
    linked, unmatched, ambiguous = mod.link_outcomes_to_candidates(outcomes, candidates)
    assert len(linked) == 2
    assert unmatched == 1 and ambiguous == 1
    eligible, research = mod.classify_outcomes_by_gate(outcomes, candidates)
    assert [x['candidate_event_id'] for x in eligible] == ['cand-A']
    assert len(research) == 2


def test_win_rate_claim_requires_minimum_sample_and_clean_linkage():
    args = dict(resolved=30, win_rate_pct=90.0, unmatched_outcomes=0,
                ambiguous_outcomes=0, unscorable_outcomes=0)
    assert mod.win_rate_target_met(**args, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met(**{**args, 'win_rate_pct':90.01}, minimum_resolved=30, target_pct=90.0) is True
    assert mod.win_rate_target_met(**{**args, 'resolved':29}, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met(**{**args, 'unmatched_outcomes':1}, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met(**{**args, 'unscorable_outcomes':1}, minimum_resolved=30, target_pct=90.0) is False


def test_preapproval_paper_cohort_does_not_change_official_gate_classification():
    outcomes=[{'candidate_event_id':'cand-paper','candidate_time':100,'outcome':'wins'}]
    candidates=[{'candidate_event_id':'cand-paper','candidate_time':100,
                 'final_gate_decision':'NO_TRADE','preapproval_paper_eligible':True}]
    eligible,research=mod.classify_outcomes_by_gate(outcomes,candidates)
    assert eligible == []
    assert len(research) == 1
    linked,unmatched,ambiguous=mod.link_outcomes_to_candidates(outcomes,candidates)
    preapproval=[row for row,c in linked if c.get('preapproval_paper_eligible') is True]
    assert preapproval == outcomes
    assert unmatched == 0 and ambiguous == 0

def test_timeout_scoring_uses_linked_candidate_geometry_like_evaluator():
    outcome = {
        'candidate_event_id':'cand-timeout',
        'direction':'SHORT',
        'outcome':'timeouts',
        'reason':'MAX_HOLD_24H',
        'exit_price':100.0,
        'exit_close':100.0,
    }
    candidate = {
        'candidate_event_id':'cand-timeout',
        'direction':'SHORT',
        'entry':99.0,
        'stop_loss':102.0,
        'take_profit':90.0,
    }
    metrics = mod.economic_counts([outcome], {id(outcome):candidate}, cost_side=0.0)
    assert metrics['timeouts'] == 1
    assert metrics['losses'] == 1
    assert metrics['resolved'] == 1
    assert metrics['unscorable'] == 0


def test_unlinked_timeout_without_candidate_geometry_stays_unscorable():
    outcome = {
        'direction':'SHORT',
        'outcome':'timeouts',
        'reason':'MAX_HOLD_24H',
        'exit_price':100.0,
        'exit_close':100.0,
    }
    metrics = mod.economic_counts([outcome], {}, cost_side=0.0)
    assert metrics['timeouts'] == 1
    assert metrics['losses'] == 0
    assert metrics['resolved'] == 0
    assert metrics['unscorable'] == 1


def _family_cohort_report(updated_at=None):
    from datetime import datetime, timezone
    profiles = mod.FAMILY_PROFILES
    summaries = {}
    details = {}
    for family_id, profile in profiles.items():
        summaries[family_id] = {
            'family_id': family_id,
            'family_version': profile.version,
            'candidate_count': 0,
            'resolved_outcome_count': 0,
            'pending_candidate_count': 0,
            'acceptance_eligible_candidate_count': 0,
            'acceptance_eligible_metrics': {},
            'research_shadow_metrics': {},
            'acceptance_status': 'NOT_MET',
            'acceptance_blockers': ['MINIMUM_100_RESOLVED_TRADES_NOT_MET'],
            'execution_enabled': False,
            'orders_placed': False,
        }
        detail = {
            'schema': 'hes_strategy_family_evaluation_report_v1',
            'status': 'NOT_MET',
            'family_id': family_id,
            'family_version': profile.version,
            'cohort_family_ids': [family_id],
            'execution_enabled': False,
            'orders_placed': False,
            'report_sha256': '',
        }
        detail['report_sha256'] = mod._canonical_report_sha(detail)
        detail['source_hashes'] = {'decision_journal_sha256':None,'candidate_ledger_sha256':None,'outcome_ledger_sha256':None,'paper_cost_context_sha256':None,'market_data_rows_sha256':'d'*64}
        detail['report_sha256'] = mod._canonical_report_sha(detail)
        details[family_id] = detail
    report = {
        'schema': 'hes_strategy_family_paper_reconciliation_v1',
        'version': 'hes-strategy-family-paper-cohort-v1.0.0',
        'updated_at': updated_at or datetime.now(timezone.utc).isoformat(),
        'status': 'NO_FAMILY_CANDIDATES_YET',
        'candidate_records': 0,
        'outcome_records': 0,
        'families': summaries,
        'family_reports': details,
        'family_acceptance': {
            'schema': 'hes_strategy_family_acceptance_result_v1',
            'status': 'NOT_MET',
            'activation_authorized': False,
            'execution_enabled': False,
            'orders_placed': False,
        },
        'acceptance_is_independent_per_family': True,
        'timestamp_fallback_matching': False,
        'execution_enabled': False,
        'orders_placed': False,
        'risk_gate_modified': False,
        'live_trading_authorized': False,
        'source_hashes': {'decision_journal_sha256':None,'candidate_ledger_sha256':None,'outcome_ledger_sha256':None,'paper_cost_context_sha256':None,'market_data_rows_sha256':'d'*64},
        'report_sha256': '',
    }
    report['report_sha256'] = mod._canonical_report_sha(report)
    return report


def test_family_paper_reconciliation_report_requires_valid_outer_and_per_family_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'DATA', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    report = _family_cohort_report()
    (tmp_path / 'strategy_family_paper_reconciliation_v1.json').write_text(json.dumps(report))
    result = mod.read_family_paper_reconciliation()
    assert result['status'] == 'VERIFIED'
    assert result['fresh'] is True
    assert set(result['families']) == {'trend_breakout', 'range_mean_reversion'}
    assert result['family_acceptance_status'] == 'NOT_MET'


def test_family_paper_reconciliation_rejects_tampered_report_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'DATA', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    report = _family_cohort_report()
    report['candidate_records'] = 1
    (tmp_path / 'strategy_family_paper_reconciliation_v1.json').write_text(json.dumps(report))
    result = mod.read_family_paper_reconciliation()
    assert result['status'] == 'INVALID'
    assert result['reason'] == 'REPORT_HASH_MISMATCH'


def test_family_paper_reconciliation_marks_stale_report_and_does_not_create_family_claims(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(mod, 'DATA', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    report = _family_cohort_report((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
    (tmp_path / 'strategy_family_paper_reconciliation_v1.json').write_text(json.dumps(report))
    result = mod.read_family_paper_reconciliation()
    assert result['status'] == 'STALE'
    assert result['fresh'] is False
    hypotheses = mod.family_cohort_hypotheses(result)
    assert len(hypotheses) == 1
    assert hypotheses[0]['status'] == 'HYPOTHESIS_ONLY'
    assert hypotheses[0]['type'] == 'FAMILY_COHORT_PIPELINE_DIAGNOSTIC'


def test_family_cohort_hypotheses_keep_trend_and_range_separate():
    snapshot = {
        'status': 'VERIFIED',
        'fresh': True,
        'families': {
            'trend_breakout': {'acceptance_status':'NOT_MET','candidate_count':12,'resolved_outcome_count':4,'acceptance_blockers':['MINIMUM_100_RESOLVED_TRADES_NOT_MET']},
            'range_mean_reversion': {'acceptance_status':'NOT_MET','candidate_count':3,'resolved_outcome_count':1,'acceptance_blockers':['VERIFIED_FEE_SLIPPAGE_MODEL_MISSING']},
        },
    }
    hypotheses = mod.family_cohort_hypotheses(snapshot)
    assert {row['family_id'] for row in hypotheses} == {'trend_breakout','range_mean_reversion'}
    assert len({row['hypothesis_id'] for row in hypotheses}) == 2
    assert all(row['status'] == 'HYPOTHESIS_ONLY' for row in hypotheses)


def test_family_paper_reconciliation_rejects_source_file_changed_after_report(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'DATA', tmp_path)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    report = _family_cohort_report()
    (tmp_path / 'trade_journal_v2.jsonl').write_text('{"event_id":"new"}\\n')
    (tmp_path / 'strategy_family_paper_reconciliation_v1.json').write_text(json.dumps(report))
    result = mod.read_family_paper_reconciliation()
    assert result['status'] == 'INVALID'
    assert result['reason'] == 'SOURCE_HASH_MISMATCH'

def test_four_family_learning_hypotheses_are_evidence_attributed_and_non_mutating(monkeypatch):
    families={}
    for family_id in ("trend_continuation","breakout_retest","range_reversion","volatility_expansion"):
        families[family_id]={
            "status":"NOT_ELIGIBLE","direction":None,
            "features":{"feature_x":False,"feature_y":True},
            "reason_codes":["FEATURE_NOT_MET"],"evidence_sha256":"a"*64,
        }
    assessment={"status":"ASSESSED","families":families}
    monkeypatch.setattr(mod,"read_decision_journal",lambda *args,**kwargs:{
        "status":"VERIFIED","events":[{"strategy_family_research_assessment":assessment}]
    })
    result=mod.family_research_hypotheses()
    assert {x["family_id"] for x in result}=={
        "trend_continuation","breakout_retest","range_reversion","volatility_expansion"
    }
    assert all(x["status"]=="HYPOTHESIS_ONLY" for x in result)
    assert all(x["feature_failure_counts"]=={"feature_x":1} for x in result)
    assert all("Do not relax thresholds" in x["proposal"] for x in result)


def test_four_family_learning_fails_closed_when_journal_not_verified(monkeypatch):
    monkeypatch.setattr(mod,"read_decision_journal",lambda *args,**kwargs:{"status":"BLOCKED","events":[]})
    result=mod.family_research_hypotheses()
    assert len(result)==1
    assert result[0]["type"]=="FOUR_FAMILY_RESEARCH_JOURNAL_DIAGNOSTIC"
    assert result[0]["status"]=="HYPOTHESIS_ONLY"
