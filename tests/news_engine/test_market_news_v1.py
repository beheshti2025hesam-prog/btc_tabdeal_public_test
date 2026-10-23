from datetime import datetime,timezone,timedelta
import pytest
from core.news_engine.market_news_v1 import NewsItem,analyze_news,brief_json
NOW=datetime(2026,10,23,18,0,tzinfo=timezone.utc)
def item(i,title,**kw):
 d=dict(item_id=i,title=title,source="Official Source",published_at=(NOW-timedelta(minutes=10)).isoformat(),asset_tags=("BTC",),venue_profile="CRYPTO_GLOBAL",source_tier="PRIMARY",verified=True); d.update(kw); return NewsItem(**d)
def test_relevant_verified_high_impact_summary():
 b=analyze_news([item("1","BTC ETF inflow approval")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.eligible_count==1 and b.status=="REQUIRES_CONFIRMATION" and b.impact=="HIGH" and "DO_NOT_TRADE_ON_HEADLINE_ALONE" in b.risk_flags and len(b.input_sha256)==64
def test_stale_excluded():
 b=analyze_news([item("1","BTC bullish rally",published_at=(NOW-timedelta(days=2)).isoformat())],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.eligible_count==0 and b.stale_count==1 and b.status=="INSUFFICIENT_EVIDENCE"
def test_unverified_does_not_affect_sentiment():
 b=analyze_news([item("1","BTC hack",verified=False,source_tier="UNVERIFIED")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.eligible_count==0 and b.sentiment_score==0 and b.confidence==0
def test_irrelevant_excluded():
 b=analyze_news([item("1","Local weather forecast",asset_tags=("WEATHER",),venue_profile="LOCAL_EQUITIES")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.eligible_count==0 and "NO_VERIFIED_FRESH_RELEVANT_NEWS" in b.risk_flags
def test_duplicates_deduplicated():
 b=analyze_news([item("1","BTC bullish rally"),item("2","BTC bullish rally")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.duplicate_count==1 and b.eligible_count==1
def test_naive_timestamp_untrusted():
 b=analyze_news([item("1","BTC rally",published_at="2026-10-23T18:00:00")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert b.eligible_count==0 and "TIMESTAMP_UNTRUSTED" in b.risk_flags
def test_duplicate_ids_rejected():
 with pytest.raises(ValueError,match="INVALID_OR_DUPLICATE_ITEM_ID"): analyze_news([item("x","BTC rally"),item("x","BTC ban")],market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
def test_deterministic_output():
 a=[item("1","BTC bullish rally")]; b=analyze_news(a,market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW)
 assert brief_json(b)==brief_json(analyze_news(a,market_profile="CRYPTO_GLOBAL",assets=["BTC"],now=NOW))
