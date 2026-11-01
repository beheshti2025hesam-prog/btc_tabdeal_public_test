from forward.strategy_policy_v2 import evaluate, POLICY_VERSION

def base(tf, e50, e200, close, rsi, mfi, breakout, side):
    return {'candle_closed':True,'close':close,'ema50':e50,'ema200':e200,'atr14':2.0,'rsi14':rsi,'mfi14':mfi,'vwap20':close-1 if side=='ABOVE' else close+1,'close_vs_ema50':side,'close_vs_vwap20':side,'close_breakout20':breakout}

def test_missing_timeframe_fails_closed():
    d=evaluate({'15m':{},'1h':{}}); assert d.decision=='NO_TRADE' and not d.execution_enabled

def test_unknown_candle_fails_closed():
    f={'15m':base('15m',110,100,120,60,65,'UP','ABOVE'),'1h':base('1h',110,100,120,60,65,'NONE','ABOVE'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}; f['15m']['candle_closed']=False
    assert evaluate(f).decision=='NO_TRADE'

def test_aligned_breakout_can_generate_paper_candidate_only():
    f={'15m':base('15m',110,100,120,60,65,'UP','ABOVE'),'1h':base('1h',110,100,120,60,65,'NONE','ABOVE'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}
    d=evaluate(f); assert d.decision=='LONG' and d.rr>=3 and d.stop_loss<d.entry<d.take_profit
    assert d.execution_enabled is False and d.orders_placed is False and d.policy_version==POLICY_VERSION

def test_conflicting_htf_blocks_signal():
    f={'15m':base('15m',110,100,120,60,65,'UP','ABOVE'),'1h':base('1h',90,100,120,40,35,'NONE','BELOW'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}
    assert evaluate(f).decision=='NO_TRADE'

def test_momentum_failure_blocks_even_with_breakout():
    f={'15m':base('15m',110,100,120,49,65,'UP','ABOVE'),'1h':base('1h',110,100,120,60,65,'NONE','ABOVE'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}
    assert evaluate(f).decision=='NO_TRADE'

def test_invalid_atr_blocks_signal():
    f={'15m':base('15m',110,100,120,60,65,'UP','ABOVE'),'1h':base('1h',110,100,120,60,65,'NONE','ABOVE'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}; f['15m']['atr14']=0
    assert evaluate(f).decision=='NO_TRADE'

def test_risk_fraction_capped():
    f={'15m':base('15m',110,100,120,60,65,'UP','ABOVE'),'1h':base('1h',110,100,120,60,65,'NONE','ABOVE'),'4h':base('4h',110,100,120,60,65,'NONE','ABOVE')}
    assert evaluate(f,risk_fraction=.02).decision=='NO_TRADE'
