import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from forward.risk_policy_v1 import RiskPolicyV1
from forward.strategy_gate_pipeline_v1 import inspect_structure, evaluate_gate_evidence
from forward.strategy_policy_v2 import PolicyDecision, POLICY_VERSION

def candles():
    vals=[100,102,105,101,99,98,103,107,104,101,97,95,99,103,108,105,102,98,94,97,101,106,103,100,96,99,104,109,105,102,98,95,99,104,110,106,102,98,94,97,101,107,104,100,96,99,103,108,104,100]
    start=datetime(2026,10,26,tzinfo=timezone.utc)
    out=[]
    for i,c in enumerate(vals):
        t=start+timedelta(minutes=15*i)
        out.append({'open_time':int(t.timestamp()),'close_time':int((t+timedelta(minutes=15)).timestamp()),'open':c,'high':c+1,'low':c-1,'close':c,'volume':10,'closed':True})
    return out

def test_structure_is_diagnostic_and_uses_confirmed_pivots():
    rows=candles(); r=inspect_structure(rows,rows[-1]['close_time'])
    assert r['status'] in ('OBSERVED','UNKNOWN')
    assert r['swing_count']>=0
    assert 'causal swing policy' in r['policy_note']

def test_gate_pipeline_fails_closed_when_risk_context_is_missing():
    p=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    rows=candles(); now=rows[-1]['close_time']
    frames={'15m':rows,'1h':rows,'4h':rows}
    r=evaluate_gate_evidence(proposal=p,rows_15m=rows,frames=frames,source='gateio_public_spot',symbol='BTC_USDT',observed_at=now)
    assert r['risk']['state']=='RISK_REJECTED'
    assert r['final_decision']=='NO_TRADE'
    assert r['execution_enabled'] is False and r['orders_placed'] is False
    risk_checks={c['name']:c['state'] for c in r['risk']['checks']}
    assert risk_checks['confirmation_valid']=='FAIL'
    assert risk_checks['risk_context_available'] in ('PASS','UNKNOWN')
    assert risk_checks['execution_disabled']=='PASS'
    assert 'CONFIRMATION_NOT_VALID' in r['risk']['reason_codes']


def test_family_route_is_diagnostic_and_cannot_authorize_decision():
    p=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    rows=candles(); now=rows[-1]['close_time']
    frames={'15m':rows,'1h':rows,'4h':rows}
    r=evaluate_gate_evidence(proposal=p,rows_15m=rows,frames=frames,source='gateio_public_spot',symbol='BTC_USDT',observed_at=now)
    route=r['strategy_family_route']
    assert route['state'] in ('FAMILY_IDENTIFIED_NOT_AUTHORIZED','NO_FAMILY')
    assert route['candidate_generation_authorized'] is False
    assert route['execution_enabled'] is False and route['orders_placed'] is False
    assert r['final_decision']=='NO_TRADE'
    assert r['execution_enabled'] is False and r['orders_placed'] is False

def test_family_route_fails_closed_for_noncanonical_source():
    p=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    rows=candles(); now=rows[-1]['close_time']
    frames={'15m':rows,'1h':rows,'4h':rows}
    r=evaluate_gate_evidence(proposal=p,rows_15m=rows,frames=frames,source='untrusted_source',symbol='BTC_USDT',observed_at=now)
    assert r['strategy_family_route']['state']=='NO_FAMILY'
    assert 'NON_CANONICAL_MARKET_DATA_SOURCE' in r['strategy_family_route']['reason_codes']
    assert r['final_decision']=='NO_TRADE'


def test_directional_family_context_is_hashed_and_remains_non_authorizing(monkeypatch):
    from forward.opportunity_detector_v1 import OpportunityCandidate
    from forward.strategy_family_context_v1 import verify_strategy_family_context
    import forward.strategy_gate_pipeline_v1 as pipeline

    def fake_structure(rows, observed_at):
        return {
            'observed_at': observed_at.isoformat(), 'status': 'OBSERVED',
            'regime': 'UPTREND', 'labels': ['HH', 'HL'], 'swing_count': 4,
            'last_swing_high': '110', 'last_swing_low': '98',
            'events': ['BOS_BULLISH'], 'policy_note': 'test-only causal fixture',
        }

    def fake_candidate(self, *, observed_at, symbol, timeframe, regime, structure_labels=(), structure_events=()):
        return OpportunityCandidate(
            observed_at=observed_at, symbol=symbol, timeframe=timeframe,
            state='CANDIDATE_LONG', regime='UPTREND',
            structure_labels=('HH', 'HL'), structure_events=('BOS_BULLISH',),
            reason_codes=('TEST_FIXTURE',), quality_score=0.8,
        )

    monkeypatch.setattr(pipeline, 'inspect_structure', fake_structure)
    monkeypatch.setattr(pipeline.OpportunityDetectorV1, 'evaluate', fake_candidate)
    p=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    rows=candles(); now=rows[-1]['close_time']
    r=pipeline.evaluate_gate_evidence(
        proposal=p, rows_15m=rows, frames={'15m':rows,'1h':rows,'4h':rows},
        source='gateio_public_spot', symbol='BTC_USDT', observed_at=now,
    )
    assert r['risk']['state']=='RISK_APPROVED'
    assert r['strategy_family_confirmation']['state'] == r['confirmation']['state']
    assert r['strategy_family_confirmation']['family_id'] == 'trend_breakout'
    assert r['strategy_family_confirmation']['confirmation_authority'] is False
    risk_checks={c['name']:c['state'] for c in r['risk']['checks']}
    assert set(RiskPolicyV1.REQUIRED) <= set(risk_checks)
    assert all(risk_checks[name]=='PASS' for name in RiskPolicyV1.REQUIRED)
    assert r['final_decision']=='NO_TRADE'  # evidence approval is not strategy-family activation

    low_rr=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,104.0,2.0,('TEST',),{'policy':'PASS'})
    low_rr_result=pipeline.evaluate_gate_evidence(
        proposal=low_rr, rows_15m=rows, frames={'15m':rows,'1h':rows,'4h':rows},
        source='gateio_public_spot', symbol='BTC_USDT', observed_at=now,
    )
    low_rr_checks={c['name']:c['state'] for c in low_rr_result['risk']['checks']}
    assert low_rr_result['risk']['state']=='RISK_REJECTED'
    assert low_rr_checks['entry_stop_target_geometry_valid']=='PASS'
    assert low_rr_checks['risk_reward_gate_passed']=='FAIL'

    invalid_geometry=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,101.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    invalid_result=pipeline.evaluate_gate_evidence(
        proposal=invalid_geometry, rows_15m=rows, frames={'15m':rows,'1h':rows,'4h':rows},
        source='gateio_public_spot', symbol='BTC_USDT', observed_at=now,
    )
    invalid_checks={c['name']:c['state'] for c in invalid_result['risk']['checks']}
    assert invalid_result['risk']['state']=='RISK_REJECTED'
    assert invalid_checks['entry_stop_target_geometry_valid']=='FAIL'
    assert invalid_checks['risk_reward_gate_passed']=='FAIL'

    context=r['strategy_family_context']
    assert r['strategy_family_context_status']=='VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED'
    assert context['family_id']=='trend_breakout'
    assert context['direction']=='LONG'
    assert verify_strategy_family_context(context, now=datetime.fromtimestamp(now, timezone.utc))==(True, None)
    assert context['candidate_generation_authorized'] is False
    assert context['confirmation_approved'] is False
    assert context['risk_approved'] is False
    assert context['execution_enabled'] is False and context['orders_placed'] is False
    assert r['final_decision']=='NO_TRADE'


def test_family_routing_is_replay_equivalent_for_all_gate_decisions(monkeypatch):
    import forward.strategy_gate_pipeline_v1 as pipeline
    p=PolicyDecision(POLICY_VERSION,'LONG','LONG',100,100.0,98.0,106.0,3.0,('TEST',),{'policy':'PASS'})
    rows=candles(); now=rows[-1]['close_time']; frames={'15m':rows,'1h':rows,'4h':rows}
    routed=pipeline.evaluate_gate_evidence(proposal=p,rows_15m=rows,frames=frames,source='gateio_public_spot',symbol='BTC_USDT',observed_at=now)
    real_router=pipeline.route_strategy_family
    monkeypatch.setattr(pipeline,'route_strategy_family',lambda **kwargs: real_router(source='not_canonical',symbol=kwargs['symbol'],timeframe=kwargs['timeframe'],regime=kwargs['regime']))
    unrouted=pipeline.evaluate_gate_evidence(proposal=p,rows_15m=rows,frames=frames,source='gateio_public_spot',symbol='BTC_USDT',observed_at=now)
    assert routed['strategy_family_route']['family_id'] is None or routed['strategy_family_route']['family_id']=='trend_breakout' or routed['strategy_family_route']['family_id']=='range_mean_reversion'
    assert unrouted['strategy_family_route']['state']=='NO_FAMILY'
    for field in ('structure','confirmation','risk','final_decision','execution_enabled','orders_placed'):
        assert routed[field]==unrouted[field]


def test_risk_policy_json_required_checks_match_runtime_contract():
    policy_path=Path(__file__).resolve().parents[2]/'forward'/'risk_policy_v1.json'
    policy=json.loads(policy_path.read_text(encoding='utf-8'))
    assert tuple(policy['required_checks'])==RiskPolicyV1.REQUIRED



def test_structural_event_presence_uses_independent_candidate_direction_when_proposal_is_no_trade(monkeypatch):
    from forward.opportunity_detector_v1 import OpportunityCandidate
    import forward.strategy_gate_pipeline_v1 as pipeline

    observed = datetime(2026, 11, 7, 18, 15, tzinfo=timezone.utc)

    def fake_structure(rows, observed_at):
        return {
            "observed_at": observed_at.isoformat(),
            "status": "OBSERVED",
            "regime": "DOWNTREND",
            "labels": ["LL", "LH"],
            "swing_count": 4,
            "last_swing_high": "110",
            "last_swing_low": "98",
            "events": ["BOS_BEARISH"],
            "policy_note": "test-only causal fixture",
        }

    def fake_candidate(self, *, observed_at, symbol, timeframe, regime, structure_labels=(), structure_events=()):
        return OpportunityCandidate(
            observed_at=observed_at,
            symbol=symbol,
            timeframe=timeframe,
            state="CANDIDATE_SHORT",
            regime="DOWNTREND",
            structure_labels=("LL", "LH"),
            structure_events=("BOS_BEARISH",),
            reason_codes=("TEST_FIXTURE",),
            quality_score=0.8,
        )

    monkeypatch.setattr(pipeline, "inspect_structure", fake_structure)
    monkeypatch.setattr(pipeline.OpportunityDetectorV1, "evaluate", fake_candidate)

    no_trade = PolicyDecision(
        POLICY_VERSION, "NO_TRADE", "NONE", 0, None, None, None, None,
        ("NO_CONFIRMED_20_BAR_BREAKOUT",), {"closed_breakout": "FAIL"},
    )
    rows = candles()
    result = pipeline.evaluate_gate_evidence(
        proposal=no_trade,
        rows_15m=rows,
        frames={"15m": rows, "1h": rows, "4h": rows},
        source="gateio_public_spot",
        symbol="BTC_USDT",
        observed_at=observed,
    )

    checks = {item["name"]: item for item in result["confirmation"]["checks"]}
    assert checks["candidate_valid"]["state"] == "PASS"
    assert checks["direction_regime_alignment"]["state"] == "FAIL"
    assert checks["direction_regime_alignment"]["evidence_ref"] == (
        "proposal_direction:NONE;candidate_direction:SHORT;regime:DOWNTREND"
    )
    assert checks["structural_event_present"]["state"] == "PASS"
    assert checks["structural_event_present"]["evidence_ref"] == (
        "candidate_direction:SHORT;matching_event_present:True"
    )
    assert result["confirmation"]["state"] == "UNCONFIRMED"
    assert result["risk"]["state"] == "RISK_REJECTED"
    assert result["final_decision"] == "NO_TRADE"
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False


def test_four_family_research_assessment_is_diagnostic_and_does_not_change_gate_decision():
    p=PolicyDecision(POLICY_VERSION,'NO_TRADE','NONE',100,None,None,None,None,('TEST_NO_TRADE',),{'policy':'NO_TRADE'})
    rows=candles(); now=rows[-1]['close_time']
    result=evaluate_gate_evidence(
        proposal=p, rows_15m=rows, frames={'15m':rows,'1h':rows,'4h':rows},
        source='gateio_public_spot', symbol='BTC_USDT', observed_at=now,
    )
    assessment=result['strategy_family_research_assessment']
    assert assessment['status']=='BLOCKED'  # test fixture lacks persisted Gate.io provenance
    assert assessment['reason_codes']
    assert result['final_decision']=='NO_TRADE'
    assert result['execution_enabled'] is False
    assert result['orders_placed'] is False
    assert assessment['execution_enabled'] is False
    assert assessment['orders_placed'] is False


def test_family_research_pipeline_separates_market_observation_from_candle_close(monkeypatch):
    import forward.strategy_gate_pipeline_v1 as pipeline
    seen = {}
    def fake_assess(**kwargs):
        seen.update(kwargs)
        return {
            "schema": "hes_strategy_family_research_assessment_v1",
            "version": "hes-strategy-family-research-assessment-v1.1.0",
            "status": "BLOCKED", "reason_codes": ["TEST_FIXTURE"],
            "families": {}, "research_eligible_family_ids": [],
            "candidate_generation_authorized": False, "confirmation_approved": False,
            "risk_approved": False, "execution_enabled": False, "orders_placed": False,
        }
    monkeypatch.setattr(pipeline, "assess_strategy_families", fake_assess)
    rows = candles()
    close_boundary = datetime.fromtimestamp(rows[-1]["close_time"], timezone.utc)
    market_observed = close_boundary + timedelta(seconds=5)
    p = PolicyDecision(POLICY_VERSION, "NO_TRADE", "NONE", 0, None, None, None, None,
                       ("TEST_NO_TRADE",), {"policy": "NO_TRADE"})
    result = pipeline.evaluate_gate_evidence(
        proposal=p, rows_15m=rows, frames={"15m": rows, "1h": rows, "4h": rows},
        source="gateio_public_spot", symbol="BTC_USDT",
        observed_at=close_boundary,
        now_ms=int(market_observed.timestamp() * 1000),
    )
    assert seen["observed_at"] == market_observed
    assert seen["now"] == market_observed
    assert result["final_decision"] == "NO_TRADE"
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False
