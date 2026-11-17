"""Universal causal technical indicators; research-only, no trading authority."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from decimal import Decimal
from math import isfinite, log
from statistics import pstdev
from typing import Any, Iterable, Mapping, Sequence

ENGINE_VERSION = "hes-universal-adaptive-indicator-engine-v1.0.0"
DEFAULT_PERIODS = {
    "ema_fast":20,"ema_slow":50,"ema_anchor":200,"rsi":14,
    "macd_fast":12,"macd_slow":26,"macd_signal":9,"atr":14,"adx":14,
    "bollinger":20,"bollinger_deviations":2.0,"keltner":20,
    "keltner_atr_multiple":1.5,"donchian":20,"choppiness":14,
    "efficiency_ratio":20,"mfi":14,"cmf":20,"stochastic":14,
    "stochastic_smooth":3,"williams_r":14,"roc":10,"relative_volume":20,
    "cci":20,"aroon":25,"supertrend_atr_multiple":3.0,"vwap":20,"obv":20,
}
INDICATOR_REGISTRY = {
 "ema":{"family":"trend","periods":[20,50,200],"inputs":["close"],"markets":"all"},
 "adx_dmi":{"family":"trend","periods":[14],"inputs":["high","low","close"],"markets":"all"},
 "supertrend":{"family":"trend","periods":[14,3.0],"inputs":["high","low","close"],"markets":"all"},
 "aroon":{"family":"trend","periods":[25],"inputs":["high","low"],"markets":"all"},
 "rsi":{"family":"momentum","periods":[14],"inputs":["close"],"markets":"all"},
 "macd":{"family":"momentum","periods":[12,26,9],"inputs":["close"],"markets":"all"},
 "stochastic":{"family":"momentum","periods":[14,3],"inputs":["high","low","close"],"markets":"all"},
 "williams_r":{"family":"momentum","periods":[14],"inputs":["high","low","close"],"markets":"all"},
 "roc":{"family":"momentum","periods":[10],"inputs":["close"],"markets":"all"},
 "cci":{"family":"momentum","periods":[20],"inputs":["high","low","close"],"markets":"all"},
 "atr":{"family":"volatility","periods":[14],"inputs":["high","low","close"],"markets":"all"},
 "bollinger":{"family":"volatility","periods":[20,2],"inputs":["close"],"markets":"all"},
 "keltner":{"family":"volatility","periods":[20,1.5],"inputs":["high","low","close"],"markets":"all"},
 "donchian":{"family":"volatility","periods":[20],"inputs":["high","low"],"markets":"all"},
 "choppiness":{"family":"regime","periods":[14],"inputs":["high","low","close"],"markets":"all"},
 "efficiency_ratio":{"family":"regime","periods":[20],"inputs":["close"],"markets":"all"},
 "vwap":{"family":"volume_flow","periods":[20],"inputs":["volume","quote_volume"],"markets":"venue_volume_qualified"},
 "relative_volume":{"family":"volume_flow","periods":[20],"inputs":["volume"],"markets":"venue_volume_qualified"},
 "obv":{"family":"volume_flow","periods":[20],"inputs":["close","volume"],"markets":"venue_volume_qualified"},
 "mfi":{"family":"volume_flow","periods":[14],"inputs":["high","low","close","volume"],"markets":"venue_volume_qualified"},
 "cmf":{"family":"volume_flow","periods":[20],"inputs":["high","low","close","volume"],"markets":"venue_volume_qualified"},
}
FAMILY_WEIGHTS={"trend":.20,"market_structure":.25,"momentum":.15,"volume_flow":.15,"entry_confirmation":.15,"volatility_quality":.10}
REGIME_POLICY={"adx_trend_floor":20.0,"adx_range_ceiling":18.0,"er_trend_floor":.30,"er_range_ceiling":.25,"chop_range_floor":61.8,"directional_confidence_floor":.58,"range_confidence_floor":.55,"minimum_directional_margin":.12,"minimum_bars":220}
REGIME_INDICATOR_PROFILES={
 "BULLISH":{"primary":["ema_20","ema_50","ema_200","ema_fast_slope_pct","adx_14","plus_di_14","rsi_14","macd_histogram","supertrend_direction","vwap_20","relative_volume_20","obv_change_20","atr_pct","donchian_upper_prior"],"purpose":"trend continuation and pullback context"},
 "BEARISH":{"primary":["ema_20","ema_50","ema_200","ema_fast_slope_pct","adx_14","minus_di_14","rsi_14","macd_histogram","supertrend_direction","vwap_20","relative_volume_20","obv_change_20","atr_pct","donchian_lower_prior"],"purpose":"downtrend continuation and rally-fade context"},
 "RANGE":{"primary":["bollinger_upper","bollinger_lower","bollinger_percent_b","rsi_14","stochastic_k","stochastic_d","williams_r_14","choppiness_14","adx_14","vwap_20","mfi_14","cmf_20","atr_pct"],"purpose":"range boundaries and mean-reversion context"},
 "TRANSITION":{"primary":["adx_14","plus_di_14","minus_di_14","ema_fast_slope_pct","efficiency_ratio_20","choppiness_14","atr_pct","bollinger_width_pct","donchian_upper_prior","donchian_lower_prior"],"purpose":"conflict and regime-transition diagnostics"},
 "UNKNOWN":{"primary":[],"purpose":"insufficient validated history; no active research profile"}
}

@dataclass(frozen=True)
class OHLCVBar:
 timestamp:int; open:float; high:float; low:float; close:float
 volume:float|None=None; quote_volume:float|None=None; closed:bool=True
@dataclass(frozen=True)
class IndicatorValue:
 value:float|None; status:str; reason:str|None=None
@dataclass(frozen=True)
class RegimeAssessment:
 label:str; evidence_confidence:float|None; scores:Mapping[str,float]
 reason_codes:tuple[str,...]; is_predictive_probability:bool=False
@dataclass(frozen=True)
class IndicatorSnapshot:
 schema:str; engine_version:str; venue:str; market:str; symbol:str; timeframe:str
 as_of:int; candle_count:int; data_status:str
 indicators:Mapping[str,IndicatorValue]; families:Mapping[str,Mapping[str,Any]]
 regime:RegimeAssessment; regime_profile:Mapping[str,Any]; weights:Mapping[str,float]
 volume_semantics_qualified:bool=False
 decision_authority:bool=False; signal_generation_enabled:bool=False
 risk_gate_bypass:bool=False; execution_enabled:bool=False; orders_placed:bool=False

def _finite(x):
 return isinstance(x,(int,float,Decimal)) and not isinstance(x,bool) and isfinite(float(x))
def normalize_bars(rows:Iterable[OHLCVBar|Mapping[str,Any]])->tuple[OHLCVBar,...]:
 out=[]
 for r in rows:
  b=r if isinstance(r,OHLCVBar) else OHLCVBar(r.get("timestamp",r.get("open_time",r.get("time"))),r.get("open"),r.get("high"),r.get("low"),r.get("close"),r.get("volume"),r.get("quote_volume"),r.get("closed",True))
  if isinstance(b.timestamp,bool) or not isinstance(b.timestamp,int) or b.timestamp<0: raise ValueError("invalid_timestamp")
  if not all(_finite(x) and x>0 for x in (b.open,b.high,b.low,b.close)): raise ValueError("invalid_ohlc")
  if b.high<max(b.open,b.close,b.low) or b.low>min(b.open,b.close,b.high): raise ValueError("invalid_ohlc_envelope")
  if b.volume is not None and (not _finite(b.volume) or b.volume<0): raise ValueError("invalid_volume")
  if b.quote_volume is not None and (not _finite(b.quote_volume) or b.quote_volume<0): raise ValueError("invalid_quote_volume")
  if type(b.closed) is not bool: raise ValueError("invalid_closed_flag")
  if b.closed:
   out.append(OHLCVBar(b.timestamp,float(b.open),float(b.high),float(b.low),float(b.close),
                       None if b.volume is None else float(b.volume),
                       None if b.quote_volume is None else float(b.quote_volume),True))
 if any(out[i].timestamp>=out[i+1].timestamp for i in range(len(out)-1)): raise ValueError("timestamps_not_strictly_increasing")
 return tuple(out)
def _ema(x,n):
 o=[None]*len(x)
 if len(x)>=n:
  v=sum(x[:n])/n;o[n-1]=v;a=2/(n+1)
  for i in range(n,len(x)): v=x[i]*a+v*(1-a);o[i]=v
 return o
def _wilder(x,n):
 o=[None]*len(x)
 if len(x)>=n:
  v=sum(x[:n]);o[n-1]=v
  for i in range(n,len(x)):v=v-v/n+x[i];o[i]=v
 return o
def _last(x):
 return next((float(v) for v in reversed(x) if v is not None and isfinite(v)),None)
def _iv(v,reason="INSUFFICIENT_HISTORY"):
 return IndicatorValue(float(v),"READY") if v is not None and isfinite(v) else IndicatorValue(None,"UNAVAILABLE",reason)
def _rsi(c,n):
 if len(c)<=n:return None
 d=[c[i]-c[i-1] for i in range(1,len(c))]
 g=[max(v,0) for v in d];l=[max(-v,0) for v in d]
 ag=sum(g[:n])/n;al=sum(l[:n])/n
 for i in range(n,len(g)):ag=(ag*(n-1)+g[i])/n;al=(al*(n-1)+l[i])/n
 return 100 if al==0 and ag>0 else 50 if al==ag==0 else 100-100/(1+ag/al) if al else None
def _dmi(bars,n):
 if len(bars)<=n:return None,None,None,None
 tr=[];pd=[];md=[]
 for i,b in enumerate(bars):
  if i==0:tr.append(b.high-b.low);pd.append(0.);md.append(0.);continue
  q=bars[i-1];tr.append(max(b.high-b.low,abs(b.high-q.close),abs(b.low-q.close)))
  up=b.high-q.high;dn=q.low-b.low
  pd.append(up if up>dn and up>0 else 0.);md.append(dn if dn>up and dn>0 else 0.)
 a=_wilder(tr[1:],n);p=_wilder(pd[1:],n);m=_wilder(md[1:],n)
 dx=[]
 for aa,pp,mm in zip(a,p,m):
  if aa and pp is not None and mm is not None:
   x,y=100*pp/aa,100*mm/aa;dx.append(100*abs(x-y)/(x+y) if x+y else 0.)
 aa,pp,mm=_last(a),_last(p),_last(m)
 if aa is None or aa==0:return None,None,None,None
 adx_sum=_last(_wilder(dx,n)) if len(dx)>=n else None
 return aa/n,100*pp/aa,100*mm/aa,(adx_sum/n if adx_sum is not None else None)
def calculate_indicators(bars:Sequence[OHLCVBar],periods:Mapping[str,Any]|None=None,*,volume_semantics_qualified:bool=False)->dict[str,IndicatorValue]:
 if type(volume_semantics_qualified) is not bool:raise ValueError("volume_semantics_qualified_must_be_bool")
 p=dict(DEFAULT_PERIODS);p.update(periods or {})
 if set(p)!=set(DEFAULT_PERIODS):raise ValueError("invalid_parameter_keys")
 for k,v in p.items():
  if not _finite(v) or v<=0 or (k not in ("bollinger_deviations","keltner_atr_multiple","supertrend_atr_multiple") and int(v)!=v):raise ValueError("invalid_parameter:"+k)
 c=[b.close for b in bars];h=[b.high for b in bars];l=[b.low for b in bars]
 out={}
 ef=_last(_ema(c,int(p["ema_fast"])));es=_last(_ema(c,int(p["ema_slow"])));ea=_last(_ema(c,int(p["ema_anchor"])))
 out.update(ema_20=_iv(ef),ema_50=_iv(es),ema_200=_iv(ea))
 efs=_ema(c,int(p["ema_fast"]))
 out["ema_fast_slope_pct"]=_iv(100*(efs[-1]/efs[-4]-1) if len(efs)>3 and efs[-1] and efs[-4] else None)
 out["rsi_14"]=_iv(_rsi(c,int(p["rsi"])))
 mf=_ema(c,int(p["macd_fast"]));ms=_ema(c,int(p["macd_slow"]))
 ml=[a-b if a is not None and b is not None else None for a,b in zip(mf,ms)]
 compact=[x for x in ml if x is not None];sig=_last(_ema(compact,int(p["macd_signal"])));line=_last(ml)
 out.update(macd_line=_iv(line),macd_signal=_iv(sig),macd_histogram=_iv(line-sig if line is not None and sig is not None else None))
 atr,pdi,mdi,adx=_dmi(bars,int(p["adx"]))
 out.update(atr_14=_iv(atr),atr_pct=_iv(100*atr/c[-1] if atr is not None and c else None),plus_di_14=_iv(pdi),minus_di_14=_iv(mdi),adx_14=_iv(adx))
 n=int(p["bollinger"])
 if len(c)>=n:
  w=c[-n:];mid=sum(w)/n;sd=pstdev(w);up=mid+float(p["bollinger_deviations"])*sd;lo=mid-float(p["bollinger_deviations"])*sd
  out.update(bollinger_mid=_iv(mid),bollinger_upper=_iv(up),bollinger_lower=_iv(lo),bollinger_width_pct=_iv(100*(up-lo)/mid),bollinger_percent_b=_iv((c[-1]-lo)/(up-lo) if up!=lo else .5))
 else:
  for k in ("bollinger_mid","bollinger_upper","bollinger_lower","bollinger_width_pct","bollinger_percent_b"):out[k]=_iv(None)
 ek=_last(_ema(c,int(p["keltner"])))
 for k,v in (("keltner_mid",ek),("keltner_upper",ek+float(p["keltner_atr_multiple"])*atr if ek is not None and atr is not None else None),("keltner_lower",ek-float(p["keltner_atr_multiple"])*atr if ek is not None and atr is not None else None)):out[k]=_iv(v)
 n=int(p["donchian"]);prior=bars[-n-1:-1] if len(bars)>n else ()
 out["donchian_upper_prior"]=_iv(max(x.high for x in prior) if prior else None);out["donchian_lower_prior"]=_iv(min(x.low for x in prior) if prior else None)
 n=int(p["choppiness"])
 if len(bars)>n:
  tr=[max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close)) for i,b in enumerate(bars) if i]
  hh=max(h[-n:]);ll=min(l[-n:]);chop=100*log(sum(tr[-n:])/(hh-ll))/log(n) if hh>ll and sum(tr[-n:])>0 else None
 else:chop=None
 out["choppiness_14"]=_iv(chop)
 n=int(p["efficiency_ratio"]);path=sum(abs(c[i]-c[i-1]) for i in range(len(c)-n,len(c))) if len(c)>n else None
 out["efficiency_ratio_20"]=_iv(abs(c[-1]-c[-n-1])/path if path else 0. if path is not None else None)
 vok=volume_semantics_qualified and bool(bars) and all(b.volume is not None for b in bars)
 volume_unavailable_reason="VENUE_VOLUME_UNQUALIFIED" if not volume_semantics_qualified else "VENUE_VOLUME_UNAVAILABLE"
 if vok:
  vol=[float(b.volume) for b in bars];n=int(p["relative_volume"]);avg=sum(vol[-n-1:-1])/n if len(vol)>n else None
  out["relative_volume_20"]=_iv(vol[-1]/avg if avg else None)
  obv=0.;series=[0.]
  for i in range(1,len(c)):obv+=vol[i] if c[i]>c[i-1] else -vol[i] if c[i]<c[i-1] else 0.;series.append(obv)
  n=int(p["obv"]);out.update(obv=_iv(obv),obv_change_20=_iv(series[-1]-series[-n-1] if len(series)>n else None))
  mult=[(2*b.close-b.high-b.low)/(b.high-b.low) if b.high!=b.low else 0. for b in bars];n=int(p["cmf"]);den=sum(vol[-n:])
  out["cmf_20"]=_iv(sum(mult[i]*vol[i] for i in range(len(bars)-n,len(bars)))/den if len(bars)>=n and den else None)
  n=int(p["mfi"]);typ=[(b.high+b.low+b.close)/3 for b in bars]
  if len(bars)>n:
   pos=neg=0.
   for i in range(len(bars)-n,len(bars)):
    f=typ[i]*vol[i]
    if typ[i]>typ[i-1]:pos+=f
    elif typ[i]<typ[i-1]:neg+=f
   mfi=100 if neg==0 and pos>0 else 50 if pos==neg==0 else 100-100/(1+pos/neg) if neg else None
  else:mfi=None
  out["mfi_14"]=_iv(mfi)
  if all(b.quote_volume is not None for b in bars):
   win=bars[-int(p["vwap"]):];base=sum(float(b.volume) for b in win);quote=sum(float(b.quote_volume) for b in win)
   out["vwap_20"]=_iv(quote/base if base else None)
  else:out["vwap_20"]=IndicatorValue(None,"UNAVAILABLE","VENUE_QUOTE_VOLUME_UNAVAILABLE")
 else:
  for k in ("relative_volume_20","obv","obv_change_20","cmf_20","mfi_14","vwap_20"):out[k]=IndicatorValue(None,"UNAVAILABLE",volume_unavailable_reason)
 n=int(p["stochastic"])
 if len(bars)>=n:
  hh=max(h[-n:]);ll=min(l[-n:]);k=100*(c[-1]-ll)/(hh-ll) if hh>ll else 50.
  ks=[]
  for i in range(max(n-1,len(bars)-int(p["stochastic_smooth"])),len(bars)):
   wh=max(h[i-n+1:i+1]);wl=min(l[i-n+1:i+1]);ks.append(100*(c[i]-wl)/(wh-wl) if wh>wl else 50.)
  d=sum(ks)/len(ks) if ks else k
 else:k=d=None
 out.update(stochastic_k=_iv(k),stochastic_d=_iv(d))
 n=int(p["williams_r"]);hh=max(h[-n:]) if len(h)>=n else None;ll=min(l[-n:]) if len(l)>=n else None
 out["williams_r_14"]=_iv(-100*(hh-c[-1])/(hh-ll) if hh is not None and hh>ll else -50. if hh is not None else None)
 n=int(p["roc"]);out["roc_10_pct"]=_iv(100*(c[-1]/c[-n-1]-1) if len(c)>n else None)
 n=int(p["cci"])
 if len(bars)>=n:
  t=[(b.high+b.low+b.close)/3 for b in bars[-n:]];mean=sum(t)/n;dev=sum(abs(x-mean) for x in t)/n;cci=(t[-1]-mean)/(.015*dev) if dev else 0.
 else:cci=None
 out["cci_20"]=_iv(cci)
 n=int(p["aroon"])
 if len(bars)>=n:
  hi=max(range(len(h)-n,len(h)),key=lambda i:h[i]);lo=min(range(len(l)-n,len(l)),key=lambda i:l[i])
  out.update(aroon_up_25=_iv(100*(n-(len(h)-1-hi))/n),aroon_down_25=_iv(100*(n-(len(l)-1-lo))/n))
 else:out.update(aroon_up_25=_iv(None),aroon_down_25=_iv(None))
 # Causal Supertrend recurrence, emitted only as descriptive state.
 n=int(p["atr"]);tr=[bars[0].high-bars[0].low]
 for i in range(1,len(bars)):
  b,q=bars[i],bars[i-1];tr.append(max(b.high-b.low,abs(b.high-q.close),abs(b.low-q.close)))
 atr_s=_wilder(tr[1:],n);fu=fl=None;direction=None
 for i in range(n,len(bars)):
  av=atr_s[i-1]/n if atr_s[i-1] is not None else None
  if av is None:continue
  mid=(bars[i].high+bars[i].low)/2;bu=mid+float(p["supertrend_atr_multiple"])*av;bl=mid-float(p["supertrend_atr_multiple"])*av
  if fu is None:fu,fl=bu,bl;direction=1. if bars[i].close>=mid else -1.;continue
  prev_fu,prev_fl=fu,fl
  fu=bu if bu<prev_fu or bars[i-1].close>prev_fu else prev_fu
  fl=bl if bl>prev_fl or bars[i-1].close<prev_fl else prev_fl
  if direction<0 and bars[i].close>fu:direction=1.
  elif direction>0 and bars[i].close<fl:direction=-1.
 out["supertrend_direction"]=_iv(direction)
 return out

def assess_regime(bars,indicators,policy=None):
 cfg=dict(REGIME_POLICY);cfg.update(policy or {})
 if set(cfg)!=set(REGIME_POLICY):raise ValueError("invalid_regime_policy_keys")
 if len(bars)<int(cfg["minimum_bars"]):return RegimeAssessment("UNKNOWN",None,{},("INSUFFICIENT_CLOSED_CANDLES",))
 v={k:x.value for k,x in indicators.items()};adx,pdi,mdi,er,chop,slope,ef,es=(v.get(k) for k in ("adx_14","plus_di_14","minus_di_14","efficiency_ratio_20","choppiness_14","ema_fast_slope_pct","ema_20","ema_50"))
 if any(x is None for x in (adx,pdi,mdi,er,chop,slope,ef,es)):return RegimeAssessment("UNKNOWN",None,{},("CORE_REGIME_FEATURE_UNAVAILABLE",))
 bull=bear=rng=0.
 if adx>=cfg["adx_trend_floor"]:
  strength=min(1.,(adx-cfg["adx_trend_floor"])/25+.35)
  if pdi>mdi:bull+=.35*strength
  elif mdi>pdi:bear+=.35*strength
 if slope>0:bull+=.25*min(1.,abs(slope)/.20)
 elif slope<0:bear+=.25*min(1.,abs(slope)/.20)
 if bars[-1].close>es and ef>es:bull+=.20
 elif bars[-1].close<es and ef<es:bear+=.20
 if er>=cfg["er_trend_floor"]:
  if bars[-1].close>es:bull+=.20*min(1.,er)
  elif bars[-1].close<es:bear+=.20*min(1.,er)
 if adx<=cfg["adx_range_ceiling"]:rng+=.35
 if er<=cfg["er_range_ceiling"]:rng+=.30
 if chop>=cfg["chop_range_floor"]:rng+=.35
 scores={"bullish":bull,"bearish":bear,"range":rng};total=sum(scores.values())
 if total<=0:return RegimeAssessment("TRANSITION",0.,scores,("NO_DOMINANT_REGIME_EVIDENCE",))
 order=sorted(scores.values(),reverse=True);winner=max(scores,key=scores.get);conf=scores[winner]/total;margin=(order[0]-order[1])/total
 if winner=="range" and conf>=cfg["range_confidence_floor"]:label="RANGE";reason=("LOW_TREND_STRENGTH","LOW_PATH_EFFICIENCY_OR_HIGH_CHOP")
 elif winner in ("bullish","bearish") and conf>=cfg["directional_confidence_floor"] and margin>=cfg["minimum_directional_margin"]:label="BULLISH" if winner=="bullish" else "BEARISH";reason=("DIRECTIONAL_EVIDENCE_ALIGNED",)
 else:label="TRANSITION";reason=("REGIME_EVIDENCE_MIXED_OR_WEAK",)
 return RegimeAssessment(label,round(conf,6),{k:round(v,6) for k,v in scores.items()},reason)

def _families(ind):
 groups={"trend":("ema_fast_slope_pct","adx_14","plus_di_14","minus_di_14","supertrend_direction","aroon_up_25","aroon_down_25"),
 "momentum":("rsi_14","macd_histogram","stochastic_k","williams_r_14","roc_10_pct","cci_20"),
 "volatility":("atr_pct","bollinger_width_pct","bollinger_percent_b","keltner_upper","donchian_upper_prior"),
 "volume_flow":("vwap_20","relative_volume_20","obv_change_20","mfi_14","cmf_20"),"regime":("choppiness_14","efficiency_ratio_20")}
 out={}
 for f,keys in groups.items():
  ready=[k for k in keys if k in ind and ind[k].status=="READY"];missing=[k for k in keys if k in ind and ind[k].status!="READY"]
  out[f]={"status":"READY" if ready else "UNAVAILABLE","available_features":ready,"unavailable_features":missing,"independent_vote_count":0,"note":"correlated descriptive evidence; not independent votes"}
 out["market_structure"]={"status":"EXTERNAL_EXISTING_COMPONENT","source":"existing HES Market Structure engine","independent_vote_count":0}
 out["entry_confirmation"]={"status":"NOT_COMPUTED","source":"existing confirmation pipeline","independent_vote_count":0}
 out["volatility_quality"]={"status":out["volatility"]["status"],"source_family":"volatility","independent_vote_count":0}
 return out

def _regime_profile(regime,indicators):
 cfg=REGIME_INDICATOR_PROFILES.get(regime.label,REGIME_INDICATOR_PROFILES["UNKNOWN"])
 requested=cfg["primary"]
 active=[k for k in requested if k in indicators and indicators[k].status=="READY"]
 unavailable=[k for k in requested if k not in indicators or indicators[k].status!="READY"]
 secondary=[k for k,v in indicators.items() if v.status=="READY" and k not in requested]
 return {"status":"RESEARCH_PROFILE" if regime.label!="UNKNOWN" else "WAITING_FOR_VALIDATED_HISTORY",
         "regime":regime.label,"primary_indicators":active,"unavailable_primary_indicators":unavailable,
         "secondary_diagnostics":secondary,"purpose":cfg["purpose"],
         "selection_is_trade_signal":False,"decision_authority":False,"execution_enabled":False}

def build_snapshot(rows,*,venue,market,symbol,timeframe,periods=None,regime_policy=None,volume_semantics_qualified=False):
 for n,x in (("venue",venue),("market",market),("symbol",symbol),("timeframe",timeframe)):
  if not isinstance(x,str) or not x.strip():raise ValueError(n+"_required")
 bars=normalize_bars(rows)
 if not bars:raise ValueError("no_closed_bars")
 ind=calculate_indicators(bars,periods,volume_semantics_qualified=volume_semantics_qualified);reg=assess_regime(bars,ind,regime_policy)
 return IndicatorSnapshot("hes.universal_indicator_snapshot.v1",ENGINE_VERSION,venue.lower(),market.lower(),symbol.upper(),timeframe,bars[-1].timestamp,len(bars),"CLOSED_BARS_ONLY",ind,_families(ind),reg,_regime_profile(reg,ind),FAMILY_WEIGHTS,volume_semantics_qualified)

def dashboard_payload(snapshot,*,source,input_sha256,freshness_seconds=None):
 if not isinstance(source,str) or not source.strip():raise ValueError("source_required")
 if not isinstance(input_sha256,str) or len(input_sha256)!=64 or any(c not in "0123456789abcdef" for c in input_sha256):raise ValueError("invalid_input_sha256")
 return {"schema":"hes.universal_indicator_dashboard.v1","status":"READ_ONLY_RESEARCH","engine_version":snapshot.engine_version,
 "market_identity":{"venue":snapshot.venue,"market":snapshot.market,"symbol":snapshot.symbol,"timeframe":snapshot.timeframe},
 "source":source,"input_sha256":input_sha256,"as_of":snapshot.as_of,"candle_count":snapshot.candle_count,
 "freshness_seconds":freshness_seconds,"data_status":snapshot.data_status,"volume_semantics_qualified":snapshot.volume_semantics_qualified,"regime":asdict(snapshot.regime),"regime_profile":dict(snapshot.regime_profile),
 "indicators":{k:asdict(v) for k,v in snapshot.indicators.items()},"families":dict(snapshot.families),"family_weights":dict(snapshot.weights),
 "controls":{"decision_authority":False,"signal_generation_enabled":False,"risk_gate_bypass":False,"execution_enabled":False,"orders_placed":False,"journal_write":False,"policy_mutation":False},
 "disclaimer":"Descriptive research evidence only; not a trade signal, probability, strategy approval, or execution instruction."}
