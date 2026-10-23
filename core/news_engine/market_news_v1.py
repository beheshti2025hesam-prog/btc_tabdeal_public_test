"""Deterministic market-aware news analysis; no network fetching or trading decisions."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json, re
from typing import Iterable, Mapping

@dataclass(frozen=True)
class NewsItem:
    item_id:str; title:str; source:str; published_at:str; url:str=""
    text:str=""; asset_tags:tuple[str,...]=(); venue_profile:str="CRYPTO_GLOBAL"
    source_tier:str="UNVERIFIED"; verified:bool=False
@dataclass(frozen=True)
class NewsAssessment:
    item_id:str; source:str; published_at:str; age_minutes:float|None
    sentiment:str; sentiment_score:float; relevance:float; impact:str; confidence:float; reasons:tuple[str,...]
@dataclass(frozen=True)
class MotherNewsBrief:
    schema:str; status:str; generated_at_utc:str; market_profile:str; assets:tuple[str,...]
    headline_count:int; eligible_count:int; duplicate_count:int; stale_count:int; unverified_count:int
    sentiment:str; sentiment_score:float; confidence:float; impact:str; risk_flags:tuple[str,...]
    key_points:tuple[str,...]; assessments:tuple[NewsAssessment,...]; input_sha256:str

POS={"approval":1.0,"approved":1.0,"adoption":.8,"inflow":.7,"inflows":.7,"surge":.6,"record high":.8,"partnership":.5,"bullish":1.0,"rally":.7,"upgrade":.5,"etf inflow":1.0,"growth":.4}
NEG={"hack":-1.0,"hacked":-1.0,"exploit":-1.0,"lawsuit":-.7,"ban":-1.0,"banned":-1.0,"outflow":-.7,"outflows":-.7,"liquidation":-.7,"liquidations":-.7,"breach":-1.0,"bankruptcy":-1.0,"probe":-.5,"investigation":-.5,"bearish":-1.0,"sell-off":-.8,"selloff":-.8,"rejection":-.7,"etf outflow":-1.0}
WEIGHT={"PRIMARY":1.0,"REPUTABLE":.8,"AGGREGATOR":.55,"UNVERIFIED":.25}
HIGH=("hack","exploit","ban","banned","lawsuit","etf","fed","rate decision","interest rate","sec","regulation","bankruptcy","breach","war","sanction","exchange halt","withdrawals suspended")
def _time(v):
 try:
  d=datetime.fromisoformat(v.replace("Z","+00:00"))
  return d.astimezone(timezone.utc) if d.tzinfo else None
 except (ValueError,AttributeError): return None
def _score(text):
 t=text.casefold(); hits=[w for p,w in sorted({**POS,**NEG}.items(),key=lambda x:-len(x[0])) if p in t]
 return max(-1.0,min(1.0,sum(hits)/max(1.0,len(hits)**.5))) if hits else 0.0
def analyze_news(items:Iterable[NewsItem|Mapping],*,market_profile:str,assets:Iterable[str],now:datetime|None=None,freshness_minutes:int=360,min_relevance:float=.25)->MotherNewsBrief:
 if freshness_minutes<1 or not 0<=min_relevance<=1: raise ValueError("INVALID_CONFIG")
 now=now or datetime.now(timezone.utc)
 if now.tzinfo is None: raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
 now=now.astimezone(timezone.utc); aset={str(a).upper() for a in assets}
 if not aset: raise ValueError("ASSET_REQUIRED")
 rows=[asdict(x) if isinstance(x,NewsItem) else dict(x) for x in items]
 ids=set(); seen=set(); assessments=[]; keypoints=[]; flags=set()
 dup=stale=unverified=eligible=0; total_score=total_weight=0.; high=False
 for r in rows:
  iid=r.get("item_id"); title=str(r.get("title") or "").strip(); source=str(r.get("source") or "").strip()
  if not isinstance(iid,str) or not iid or iid in ids: raise ValueError("INVALID_OR_DUPLICATE_ITEM_ID")
  ids.add(iid)
  if not title or not source: raise ValueError("TITLE_AND_SOURCE_REQUIRED")
  text=(title+" "+str(r.get("text") or "")).strip()
  fingerprint=sha256((re.sub(r"\W+"," ",title.casefold()).strip()+"|"+source.casefold()).encode()).hexdigest()
  if fingerprint in seen: dup+=1; continue
  seen.add(fingerprint); profile=str(r.get("venue_profile") or "CRYPTO_GLOBAL").upper()
  tags={str(x).upper() for x in (r.get("asset_tags") or ())}
  matched=bool(tags&aset) or any(a in text.upper() for a in aset)
  relevance=min(1.,(.7 if matched else 0.)+(.3 if profile==market_profile.upper() or profile=="GLOBAL" else 0.))
  published=str(r.get("published_at") or ""); dt=_time(published)
  age=(now-dt).total_seconds()/60 if dt else None; reasons=[]
  if age is None: reasons.append("INVALID_OR_TIMEZONE_NAIVE_TIMESTAMP")
  elif age < -5: reasons.append("FUTURE_PUBLISHED_AT")
  elif age>freshness_minutes: stale+=1; reasons.append("STALE_NEWS")
  verified=bool(r.get("verified",False)); tier=str(r.get("source_tier") or "UNVERIFIED").upper()
  if not verified or tier=="UNVERIFIED": unverified+=1; reasons.append("SOURCE_UNVERIFIED")
  score=_score(text); impact="HIGH" if any(t in text.casefold() for t in HIGH) else "MEDIUM" if abs(score)>=.45 else "LOW"
  if impact=="HIGH": high=True
  fresh=age is not None and -5<=age<=freshness_minutes
  eligible_item=fresh and verified and tier in WEIGHT and tier!="UNVERIFIED" and relevance>=min_relevance
  if eligible_item:
   eligible+=1; w=WEIGHT[tier]*relevance*max(.2,1-age/max(1,freshness_minutes))
   total_score+=score*w; total_weight+=w
   if impact=="HIGH": flags.add("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION")
   if abs(score)>=.45: keypoints.append(f"{title} [{source}; {score:+.2f}]")
  else:
   if relevance<min_relevance: reasons.append("LOW_MARKET_RELEVANCE")
   if dt is None: flags.add("TIMESTAMP_UNTRUSTED")
   if age is not None and age < -5: flags.add("FUTURE_DATED_ITEM")
  conf=WEIGHT.get(tier,.25)*relevance*(1. if fresh else .25) if verified else 0.
  assessments.append(NewsAssessment(iid,source,published,round(age,2) if age is not None else None,"POSITIVE" if score>.15 else "NEGATIVE" if score<-.15 else "NEUTRAL",round(score,3),round(relevance,3),impact,round(conf,3),tuple(reasons)))
 mean=total_score/total_weight if total_weight else 0.; confidence=min(1.,total_weight/max(1.,eligible)) if eligible else 0.
 if not eligible: flags.add("NO_VERIFIED_FRESH_RELEVANT_NEWS")
 if high: flags.add("DO_NOT_TRADE_ON_HEADLINE_ALONE")
 sentiment="POSITIVE" if mean>.15 else "NEGATIVE" if mean<-.15 else "NEUTRAL"
 status="INSUFFICIENT_EVIDENCE" if not eligible else "REQUIRES_CONFIRMATION" if "HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION" in flags else "CONTEXT_ONLY"
 raw=json.dumps(rows,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=list).encode()
 return MotherNewsBrief("hes_mother_news_brief_v1",status,now.isoformat(timespec="seconds").replace("+00:00","Z"),market_profile.upper(),tuple(sorted(aset)),len(rows),eligible,dup,stale,unverified,sentiment,round(mean,3),round(confidence,3),"HIGH" if high else "MEDIUM" if abs(mean)>=.45 else "LOW",tuple(sorted(flags)),tuple(keypoints[:8]),tuple(assessments),sha256(raw).hexdigest())
def brief_json(brief): return json.dumps(asdict(brief),sort_keys=True,separators=(",",":"),ensure_ascii=False)
