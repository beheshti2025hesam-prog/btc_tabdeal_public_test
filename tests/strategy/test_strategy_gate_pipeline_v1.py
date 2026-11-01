from datetime import datetime, timezone, timedelta
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
