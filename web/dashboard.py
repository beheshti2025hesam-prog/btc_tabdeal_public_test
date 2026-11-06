"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
import hashlib, json, os, time
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from forward.native_ohlcv_v1 import INTERVAL_MS, NativeCandle, NativeOHLCVBatch, validate_native_batch
from forward.global_market_data_reader_v1 import load_market_input, canonical_market_batch_sha256
from forward.native_ohlcv_gateio_v1 import (
    VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES, VOLUME_SEMANTICS_CONTRACT_VERSION,
    TRADE_COUNT_AVAILABLE, TAKER_BUY_FLOW_AVAILABLE,
    gateio_spot_source_symbol, verify_gateio_spot_symbol_mapping)
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.trade_journal_view_v1 import configured_decision_journal, JournalProjectionError
from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain
from core.market_intelligence.news_monitor import NewsMonitorV1
from web.strategy_v2_dashboard_view import read_strategy_v2_dashboard, StrategyV2DashboardError
from web.mother_v2_dashboard_view import read_mother_v2_dashboard, MotherV2DashboardError
from web.mother_chat_v1 import MotherChatError, MotherChatSecurityV1, build_chat_response, read_json_body
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream

SUPPORTED_SYMBOLS = {"BTCUSDT"}
CANONICAL_ANALYSIS_SYMBOL = "BTCUSDT"
GATEIO_SOURCE_SYMBOL = gateio_spot_source_symbol(CANONICAL_ANALYSIS_SYMBOL)
SUPPORTED_INTERVALS = {"1m", "15m", "1h", "4h"}
# Match the 1m integrity witness (120s) and the 15m/1h/4h soak SLA (period + 180s).
MAX_CANDLE_AGE_SECONDS = {"1m": 120, "15m": 1080, "1h": 3780, "4h": 14580}
PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _market_data_root() -> Path:
    """Resolve the shared mutable data root, separate from immutable release code."""
    configured = os.environ.get("HES_GLOBAL_MARKET_DATA_ROOT")
    return Path(configured).expanduser() if configured else PROJECT_ROOT


CHART_ASSET_PATH = "/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js"
CHART_ASSET_FILE = Path(__file__).resolve().parent / "static" / "third_party" / "lightweight-charts" / "5.0.8" / "lightweight-charts.standalone.production.js"
class PersistedGlobalFeedSource:
    """Read the same validated persisted candles used by the analysis input boundary."""
    venue = "gateio"
    product = "spot"

    def fetch(self, *, symbol, interval="15m", limit=240, start_time_ms=None, end_time_ms=None, as_of_ms=None):
        if symbol not in SUPPORTED_SYMBOLS or interval not in SUPPORTED_INTERVALS:
            raise ValueError("unsupported persisted global-feed identity")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid persisted candle limit")
        if start_time_ms is not None or end_time_ms is not None or as_of_ms is not None:
            raise ValueError("persisted global feed does not support custom time windows")
        market = load_market_input(root=_market_data_root())
        if interval == "1m":
            from forward.global_market_data_reader_v1 import read_closed_candles
            market["timeframes"]["1m"] = read_closed_candles("1m", root=_market_data_root(), min_bars=1)
        if market.get("source") != "gateio_public_spot" or not verify_gateio_spot_symbol_mapping(symbol, market.get("symbol")):
            raise ValueError("persisted global source identity mismatch")
        rows = market["timeframes"].get(interval, [])[-limit:]
        minimum = 1 if interval == "1m" else 200
        if len(rows) < minimum:
            raise ValueError("insufficient persisted closed candles")
        now_ms = int(time.time() * 1000)
        seconds = INTERVAL_MS[interval] // 1000
        candles = []
        for row in rows:
            open_time_s = int(row["open_time"])
            close_time_exclusive_s = int(row["close_time"])
            if close_time_exclusive_s != open_time_s + seconds:
                raise ValueError("persisted candle close-time contract mismatch")
            candles.append(NativeCandle(
                venue="gateio", product="spot", symbol=symbol, interval=interval,
                open_time_ms=open_time_s * 1000,
                close_time_ms=close_time_exclusive_s * 1000 - 1,
                open=Decimal(row["open"]), high=Decimal(row["high"]), low=Decimal(row["low"]),
                close=Decimal(row["close"]), volume=Decimal(row["volume"]),
                quote_volume=Decimal(row["quote_volume"]), trade_count=None,
                taker_buy_volume=None, taker_buy_quote_volume=None, closed=True,
            ))
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        batch = NativeOHLCVBatch(
            venue="gateio", product="spot", symbol=symbol, interval=interval,
            endpoint_kind="global_market_data_reader_v1", fetched_at_ms=now_ms,
            response_sha256=digest, candles=tuple(candles), gaps=(), open_candles_excluded=0,
        )
        validate_native_batch(batch)
        return batch


_SOURCE = PersistedGlobalFeedSource()
_FEATURES = NativeOHLCVFeaturePipelineV1(volume_semantics_approved=VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES)
_NEWS_BRAIN = NewsIntelligenceBrain()
_NEWS_REGISTRY = PROJECT_ROOT / "config" / "news_sources_v1.json"
_NEWS_CONTEXT = MarketContext(market="crypto", symbol="BTCUSDT", regime="unknown", timeframe="15m", venue="gateio")
_NEWS_MONITOR_INTERVAL = int(os.environ.get("HES_NEWS_MONITOR_INTERVAL_SECONDS", "300"))
_NEWS_MONITOR_SNAPSHOT = Path(os.environ.get("HES_NEWS_MONITOR_SNAPSHOT", "/var/lib/hes-news-monitor/news_brief_latest.json"))
_NEWS_MONITOR = NewsMonitorV1(
    brain=_NEWS_BRAIN, registry_path=_NEWS_REGISTRY, context=_NEWS_CONTEXT,
    snapshot_path=_NEWS_MONITOR_SNAPSHOT, interval_seconds=_NEWS_MONITOR_INTERVAL,
)
_CACHE_LOCK = Lock()
_CACHE = {}
_STREAM_STOP = Event()
_STREAM_STATE = {"status": "disabled", "reason": None, "last_event_ms": None}

def _refresh_batch(symbol, interval, event=None):
    batch = _SOURCE.fetch(symbol=symbol, interval=interval, limit=240)
    validate_native_batch(batch)
    if not batch.candles:
        raise ValueError("no_closed_candles")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    latest = batch.candles[-1]
    age_ms = now_ms - latest.close_time_ms
    if age_ms < 0 or age_ms > MAX_CANDLE_AGE_SECONDS[interval] * 1000:
        raise ValueError("latest_closed_candle_stale")
    if batch.gaps:
        raise ValueError("persisted_candle_gaps_present")
    if event is not None:
        assert_event_matches_batch(event, batch)
    feature_result = _FEATURES.build(batch)
    with _CACHE_LOCK:
        _CACHE[(symbol, interval)] = (batch, feature_result, int(time.time() * 1000))
    return batch, feature_result

def _stream_reconcile():
    try:
        _refresh_batch("BTCUSDT", "1m")
        _STREAM_STATE.update(status="history_reconciled", reason=None)
    except Exception as exc:
        _STREAM_STATE.update(status="blocked", reason=type(exc).__name__)
        raise

def _stream_payload(payload):
    event = parse_kline_event(payload, symbol="BTCUSDT", interval="1m")
    now_ms = int(time.time() * 1000)
    delay = now_ms - event.event_time_ms
    if delay < -2_000 or delay > 15_000:
        raise NativeKlineStreamError("stale_or_future_websocket_event")
    _STREAM_STATE.update(status="connected", reason=None, last_event_ms=event.event_time_ms)
    if not event.candle:
        return
    try:
        _refresh_batch("BTCUSDT", "1m", event=event)
    except Exception as exc:
        _STREAM_STATE.update(status="blocked", reason=type(exc).__name__)
        raise

def _stream_worker():
    try:
        run_spot_kline_stream(symbol="BTCUSDT", interval="1m", on_payload=_stream_payload,
                              reconcile_history=_stream_reconcile, stop_event=_STREAM_STOP)
    except Exception as exc:
        _STREAM_STATE.update(status="blocked", reason=type(exc).__name__)

def _get_batch(symbol, interval):
    now_ms = int(time.time() * 1000)
    ttl_ms = 75_000 if (symbol, interval) == ("BTCUSDT", "1m") else 15_000
    with _CACHE_LOCK:
        cached = _CACHE.get((symbol, interval))
    if cached and now_ms - cached[2] <= ttl_ms and cached[0].candles and not cached[0].gaps:
        cached_age_ms = now_ms - cached[0].candles[-1].close_time_ms
        if 0 <= cached_age_ms <= MAX_CANDLE_AGE_SECONDS[interval] * 1000:
            return cached[0], cached[1]
    return _refresh_batch(symbol, interval)

def _current_chart_batch_provenance():
    """Describe the exact cached native batches currently used by the chart."""
    timeframes = {}
    for timeframe in ("15m", "1h", "4h"):
        batch, _ = _get_batch("BTCUSDT", timeframe)
        if not batch.candles:
            raise ValueError("chart_batch_empty:" + timeframe)
        digest = batch.response_sha256
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("chart_batch_digest_invalid:" + timeframe)
        last = batch.candles[-1]
        timeframes[timeframe] = {
            "input_batch_sha256": digest,
            "candle_count": len(batch.candles),
            "last_closed_candle_time": int((last.close_time_ms + 1) // 1000),
        }
    return {
        "schema": "hes_market_data_batch_provenance_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "batch_limit": 240,
        "timeframes": timeframes,
    }

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HES Trade Agent</title><link rel="icon" href="/static/hes-mark.svg" type="image/svg+xml"><link rel="stylesheet" href="/static/dashboard.css"><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><a class="skip-link" href="#main-content">Skip to dashboard content</a><main id="main-content" tabindex="-1"><header><div class="brand-lockup"><img class="brand-mark" src="/static/hes-mark.svg" alt="" aria-hidden="true"><div><h1 class="brand">HES Trade Agent</h1><div class="sub">Global feed · persisted closed candles</div></div></div><div class="header-actions"><label class="language-control" for="languageSelect"><span>Language</span><select id="languageSelect" aria-label="Dashboard language"><option value="en">English</option><option value="fa">فارسی</option><option value="de">Deutsch</option><option value="fr">Français</option></select></label><span class="pill">HOLD / NO_TRADE_ONLY</span></div></header>
<nav class="section-nav" aria-label="Dashboard sections"><a href="#marketPanel">Market</a><a href="#precisionEntryPanel">Precision</a><a href="#strategyV2Panel">Strategy</a><a href="#motherPanel">Mother</a><a href="#motherChatPanel">Command Center</a><a href="#newsRadarPanel">News</a><a href="#safetyPanel">Safety</a><a href="#journalPanel">Journal</a></nav>
<section class="panel" id="marketPanel" aria-labelledby="marketTitle"><h2 class="panel-title" id="marketTitle">Market overview · Gate.io</h2><div class="toolbar"><label>Symbol <select id="symbol"><option>BTCUSDT</option></select></label><label>Timeframe <select id="interval"><option>15m</option><option>1m</option><option>1h</option><option>4h</option></select></label><button id="refresh">Refresh data</button><span class="muted" id="source">Canonical persisted global feed</span></div>
<div class="metrics"><div class="metric"><small>Last closed close</small><strong id="price" data-no-translate>—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" data-no-translate class="stamp">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume" data-no-translate>—</strong></div><div class="metric"><small>Closed candles</small><strong id="count" data-no-translate>—</strong></div></div>
<div class="panel chart-panel"><div id="chart" role="img" aria-label="Candlestick chart"></div></div><div id="message" role="status" aria-live="polite" aria-atomic="true">Loading validated closed candles…</div></section>
<section class="panel" id="precisionEntryPanel" aria-labelledby="precisionEntryTitle"><h2 class="panel-title" id="precisionEntryTitle">Multi-Timeframe Alignment · Precision Entry</h2><div class="metrics"><div class="metric"><small>4H data</small><strong id="pe4h" data-no-translate>Checking…</strong></div><div class="metric"><small>1H data</small><strong id="pe1h" data-no-translate>Checking…</strong></div><div class="metric"><small>15M setup gate</small><strong id="pe15m" data-no-translate>Checking…</strong></div><div class="metric"><small>1M feed</small><strong id="pe1m" data-no-translate>Checking…</strong></div><div class="metric"><small>Precision Entry</small><strong id="peState" data-no-translate>BLOCKED</strong></div><div class="metric"><small>Risk Gate</small><strong id="peRisk" data-no-translate>UNVERIFIED</strong></div></div><p class="muted" id="peReasons" data-no-translate role="status" aria-live="polite">Waiting for validated multi-timeframe evidence…</p><div class="gate"><strong>Advisory only · execution disabled</strong><p class="muted">The 15M setup remains authoritative. The 1M layer cannot create a trade, change direction, bypass Risk Gate, or submit orders. Missing/stale candles, missing provenance-bound entry context, or unapproved setup means BLOCKED / NO_TRADE.</p></div></section>
<section class="panel" id="strategyV2Panel" aria-labelledby="strategyV2Title"><h2 class="panel-title" id="strategyV2Title">Canonical Strategy V2 · Paper evaluator</h2><div class="metrics"><div class="metric"><small>Canonical decision</small><strong id="v2Decision" data-no-translate>NO_TRADE</strong></div><div class="metric"><small>Evidence status</small><strong id="v2Status" data-no-translate role="status" aria-live="polite">Checking report…</strong></div><div class="metric"><small>Market regime</small><strong id="v2Regime" data-no-translate>UNKNOWN</strong></div><div class="metric"><small>Policy version</small><strong id="v2Version" data-no-translate>—</strong></div><div class="metric"><small>Paper outcomes</small><strong id="v2Outcomes" data-no-translate>—</strong></div><div class="metric"><small>Decision journal</small><strong id="v2Journal" data-no-translate>—</strong></div></div><p class="muted" id="v2Reasons" data-no-translate>Waiting for the canonical V2 evaluator report…</p><div class="gate"><strong>Gate.io data only · execution disabled</strong><p class="muted" id="v2Evidence" data-no-translate>This panel is a read-only projection of the existing Strategy Policy V2 evaluator and canonical journal. It does not calculate a second strategy or submit orders.</p></div></section>
<section class="panel" id="motherPanel" aria-labelledby="motherTitle"><h2 class="panel-title" id="motherTitle">Mother Orchestrator · canonical V2 evidence chain</h2><div class="metrics"><div class="metric"><small>Orchestration</small><strong id="motherStatus" data-no-translate role="status" aria-live="polite">BLOCKED</strong></div><div class="metric"><small>Independent witness</small><strong id="motherWitness" data-no-translate>NOT VERIFIED</strong></div><div class="metric"><small>Trace / audit</small><strong id="motherTrace" data-no-translate>—</strong></div></div><p class="muted" id="motherReasons" data-no-translate>Waiting for matched Strategy V2 report and journal evidence…</p><ul id="motherStages" data-no-translate><li class="muted">No verified orchestration stages.</li></ul><div class="gate"><strong>Observation only · execution disabled</strong><p class="muted" id="motherEvidence" data-no-translate>Mother coordinates the existing Strategy V2 specialist outputs. It does not recalculate market data, indicators, strategy or risk, and cannot authorize orders.</p></div></section>
<section class="panel" id="motherChatPanel" aria-labelledby="motherChatTitle"><h2 class="panel-title" id="motherChatTitle">Mother Command Center · free local interface</h2><p class="muted">Bounded read-only commands over existing HES evidence. No paid API, external LLM, account access, order tools, policy changes or journal writes. Chat history stays in this page only.</p><div id="motherChatLogin"><form id="motherChatLoginForm"><label for="motherChatToken">Local access token</label><input id="motherChatToken" type="password" autocomplete="current-password" maxlength="256" required><button id="motherChatUnlock" type="submit">Unlock Command Center</button><p class="muted" id="motherChatLoginStatus" role="status" aria-live="polite">Access is disabled until the operator configures the local token file.</p></form></div><div id="motherChatWorkspace" hidden><div id="motherChatMessages" class="mother-chat-messages" role="log" aria-live="polite" aria-relevant="additions text"><p class="muted">Ask about status, a decision, the market, journal, news or diagnostics.</p></div><form id="motherChatForm"><label for="motherChatInput">Message Mother</label><textarea id="motherChatInput" rows="2" maxlength="1000" required placeholder="مثلاً: چرا تصمیم مادر عدم ترید است؟"></textarea><div class="mother-chat-actions"><button id="motherChatSend" type="submit">Send</button><button id="motherChatLogout" type="button" class="secondary">Lock</button></div></form></div><div class="gate"><strong>Safety boundary</strong><p class="muted">Mother explains recorded evidence; it does not create a new signal. Gate.io Public Spot BTC_USDT remains the sole analysis source. Execution, account access and all write actions remain disabled.</p></div></section>
<section class="panel" id="newsRadarPanel" aria-labelledby="newsTitle"><h2 class="panel-title" id="newsTitle">News Radar · read-only evidence</h2><div class="metrics"><div class="metric"><small>Monitor</small><strong id="newsStatus" data-no-translate role="status" aria-live="polite">BLOCKED</strong></div><div class="metric"><small>Qualified coverage</small><strong id="newsCoverage" data-no-translate>UNKNOWN</strong></div><div class="metric"><small>Sources OK / empty / failed</small><strong id="newsSources" data-no-translate>0 / 0 / 0</strong></div><div class="metric"><small>International / domestic / venue</small><strong id="newsScopes" data-no-translate>0 / 0 / 0</strong></div><div class="metric"><small>Fresh / aging / stale / future / empty / failed / unknown</small><strong id="newsFreshness" data-no-translate>0 / 0 / 0 / 0 / 0 / 0 / 0</strong></div><div class="metric"><small>Last poll (UTC)</small><strong id="newsLastPoll" data-no-translate>—</strong></div></div><p class="muted" id="newsSummary" data-no-translate>Waiting for verified news evidence…</p><p class="muted" id="newsFlags" data-no-translate>News does not originate trade direction or authorize execution.</p><ul id="newsItems" data-no-translate><li class="muted">No verified headlines loaded.</li></ul><h3>Per-source health and freshness</h3><ul id="newsSourceDetails" data-no-translate><li class="muted">No per-source health loaded.</li></ul><div class="gate"><strong>Context only · no trade authorization</strong><p class="muted">Gate.io remains the sole live market-data source. Gate.io announcements are venue-operational news only; candles, indicators and chart data never come from news feeds. News coverage is explicitly partial where shown.</p></div></section>
<section class="panel" id="safetyPanel" aria-labelledby="safetyTitle"><h2 class="panel-title" id="safetyTitle">Decision and safety gates</h2><div class="gate"><strong>Execution: disabled</strong><p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<section class="panel" id="journalPanel" aria-labelledby="journalTitle"><div class="toolbar"><div><h2 class="panel-title" id="journalTitle">Trade Journal · Decision & Learning Evidence</h2><div class="muted">Immutable forward decisions only. Executed trades and realized outcomes are not inferred from a signal.</div></div><button id="journalRefresh" type="button">Refresh journal</button></div><p class="muted" id="journalStatus" role="status" aria-live="polite" aria-atomic="true">Loading journal…</p><div class="journal-scroll"><table class="journal-table"><caption class="sr-only">Latest immutable forward decision events and their evidence references</caption><thead><tr><th scope="col">Time (UTC)</th><th scope="col">Market</th><th scope="col">Decision</th><th scope="col">Strategy family</th><th scope="col">Gate / reason</th><th scope="col">Outcome</th><th scope="col">Evidence</th></tr></thead><tbody id="journalRows" data-no-translate><tr><td colspan="7" class="muted">No journal entries loaded.</td></tr></tbody></table></div></section>
<div class="footer"><span>Charts powered by</span> <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. <span>Copyright (c) 2025 TradingView, Inc.</span> <span>The chart reads the same validated persisted Gate.io candles through the canonical global-market reader used by the analysis input path; the dashboard does not make a second REST candle request. This is a single public venue source, not a cross-venue consolidated index. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Base and quote volume fields follow Gate.io's documented candlestick schema and are shown unchanged; trade count and taker-buy flow are unavailable. If the source is unavailable or stale, the chart fails closed.</span><span class="copyright" lang="en" dir="ltr" data-no-translate><span class="brand-footer-name">HES Trade Agent</span><span class="copyright-notice">Copyright © HES Trade Agent. All rights reserved.</span><span class="owner-name">SEYED HESAMEDDIN BEHESHTI SHIRAZI</span><span class="owner-role">Designer &amp; Owner</span></span></div></main>
<script src="/static/dashboard.js" defer></script></body></html>'''



_MOTHER_CHAT_SECURITY = MotherChatSecurityV1()


def _mother_chat_core_evidence():
    provenance = _current_chart_batch_provenance()
    strategy = read_strategy_v2_dashboard(current_market_data_provenance=provenance)
    mother = read_mother_v2_dashboard(strategy_view=strategy)
    return strategy, mother


def _mother_chat_journal_evidence():
    journal_path = os.environ.get(
        "HES_TRADE_JOURNAL_PATH",
        str(PROJECT_ROOT / "data" / "forward" / "trade_journal_v2.jsonl"),
    )
    return configured_decision_journal(journal_path=journal_path, limit=20)


def _mother_chat_news_evidence():
    return _NEWS_MONITOR.read_snapshot(max_age_seconds=max(600, _NEWS_MONITOR_INTERVAL * 3))


def _mother_chat_readers():
    def status_reader():
        strategy, mother = _mother_chat_core_evidence()
        try:
            news = _mother_chat_news_evidence()
        except Exception:
            news = {"monitor": {"status": "BLOCKED"}}
        return {
            "strategy": strategy, "mother": mother, "news": news,
            "trace_id": mother.get("trace_id"),
            "evidence_refs": [x for x in (
                mother.get("trace_id"), mother.get("audit_sha256"),
                strategy.get("report_sha256"), mother.get("journal_event_sha256"),
            ) if isinstance(x, str) and x],
        }

    def explain_reader():
        strategy, mother = _mother_chat_core_evidence()
        return {
            "strategy": strategy, "mother": mother,
            "trace_id": mother.get("trace_id"),
            "evidence_refs": [x for x in (
                mother.get("trace_id"), mother.get("audit_sha256"),
                strategy.get("report_sha256"),
            ) if isinstance(x, str) and x],
        }

    def market_reader():
        strategy, mother = _mother_chat_core_evidence()
        batch, _ = _get_batch("BTCUSDT", "15m")
        if not batch.candles:
            raise ValueError("closed_market_candles_missing")
        latest = batch.candles[-1]
        age = (int(datetime.now(timezone.utc).timestamp() * 1000) - latest.close_time_ms) / 1000
        if batch.gaps or age < 0 or age > MAX_CANDLE_AGE_SECONDS["15m"]:
            raise ValueError("closed_market_candles_stale_or_gapped")
        return {
            "strategy": strategy,
            "latest_candle": {"close": str(latest.close), "age_seconds": age},
            "trace_id": mother.get("trace_id"),
            "evidence_refs": [x for x in (
                strategy.get("report_sha256"), mother.get("trace_id"),
                batch.response_sha256,
            ) if isinstance(x, str) and x],
        }

    def journal_reader():
        journal = _mother_chat_journal_evidence()
        try:
            strategy, mother = _mother_chat_core_evidence()
        except Exception:
            strategy, mother = {}, {}
        return {
            "journal": journal, "strategy": strategy,
            "trace_id": mother.get("trace_id"),
            "evidence_refs": [x for x in (
                journal.get("journal_sha256") if isinstance(journal, dict) else None,
                strategy.get("report_sha256") if isinstance(strategy, dict) else None,
                mother.get("trace_id") if isinstance(mother, dict) else None,
            ) if isinstance(x, str) and x],
        }

    def news_reader():
        news = _mother_chat_news_evidence()
        monitor = news.get("monitor", {}) if isinstance(news, dict) else {}
        return {
            "news": news,
            "evidence_refs": [x for x in (
                monitor.get("snapshot_sha256") if isinstance(monitor, dict) else None,
            ) if isinstance(x, str) and x],
        }

    def diagnose_reader():
        components = {}
        try:
            batch, _ = _get_batch("BTCUSDT", "15m")
            age = (int(datetime.now(timezone.utc).timestamp() * 1000) - batch.candles[-1].close_time_ms) / 1000 if batch.candles else None
            feed_ok = bool(batch.candles) and not batch.gaps and age is not None and 0 <= age <= MAX_CANDLE_AGE_SECONDS["15m"]
            components["Gate.io 15m feed"] = {"status": "OK" if feed_ok else "BLOCKED", "reason": None if feed_ok else "stale_or_gapped"}
        except Exception:
            components["Gate.io 15m feed"] = {"status": "BLOCKED", "reason": "evidence_unavailable"}
        try:
            strategy, mother = _mother_chat_core_evidence()
            components["Strategy V2"] = {"status": strategy.get("status", "UNKNOWN")}
            witness = mother.get("witness", {})
            witness_ok = isinstance(witness, dict) and witness.get("verified") is True
            components["Mother witness"] = {"status": "VERIFIED" if witness_ok and mother.get("status") == "OBSERVATION_ONLY" else "BLOCKED"}
            trace_id = mother.get("trace_id", "")
        except Exception:
            components["Strategy V2"] = {"status": "BLOCKED", "reason": "evidence_unavailable"}
            components["Mother witness"] = {"status": "BLOCKED", "reason": "evidence_unavailable"}
            trace_id = ""
        try:
            journal = _mother_chat_journal_evidence()
            components["Decision journal"] = {"status": journal.get("status", "UNKNOWN")}
        except Exception:
            components["Decision journal"] = {"status": "BLOCKED", "reason": "evidence_unavailable"}
        try:
            news = _mother_chat_news_evidence()
            monitor = news.get("monitor", {})
            components["News Radar"] = {"status": monitor.get("status", "UNKNOWN") if isinstance(monitor, dict) else "UNKNOWN"}
        except Exception:
            components["News Radar"] = {"status": "BLOCKED", "reason": "evidence_unavailable"}
        return {"components": components, "trace_id": trace_id}

    return {
        "ASK_STATUS": status_reader,
        "EXPLAIN_DECISION": explain_reader,
        "MARKET_REVIEW": market_reader,
        "JOURNAL_REVIEW": journal_reader,
        "NEWS_CONTEXT": news_reader,
        "DIAGNOSE": diagnose_reader,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "HESReadOnlyDashboard/1.0"
    def _send(self,status,body,content_type,extra_headers=None):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
        for header, value in (extra_headers or []):
            self.send_header(header, value)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/":
            return self._send(200,HTML.encode(),"text/html; charset=utf-8")
        if p.path==CHART_ASSET_PATH:
            try:
                asset=CHART_ASSET_FILE.read_bytes()
            except OSError:
                return self._send(503,b'{"error":"chart_library_unavailable","fail_closed":true}',"application/json")
            return self._send(200,asset,"text/javascript; charset=utf-8")
        static_assets = {
            "/static/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
            "/static/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
            "/static/hes-mark.svg": ("hes-mark.svg", "image/svg+xml; charset=utf-8"),
        }
        if p.path in static_assets:
            filename, content_type = static_assets[p.path]
            asset_path = Path(__file__).resolve().parent / "static" / filename
            try:
                asset = asset_path.read_bytes()
            except OSError:
                return self._send(503,b'{"error":"dashboard_asset_unavailable","fail_closed":true}',"application/json")
            return self._send(200,asset,content_type)
        if p.path=="/healthz":
            try:
                batch, _ = _get_batch("BTCUSDT", "15m")
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                latest_age_seconds = (now_ms - batch.candles[-1].close_time_ms) / 1000
                if latest_age_seconds < 0 or latest_age_seconds > MAX_CANDLE_AGE_SECONDS["15m"]:
                    raise ValueError("latest_closed_candle_stale")
                if batch.gaps:
                    raise ValueError("persisted_candle_gaps_present")
                payload = {
                    "status": "ok", "mode": "NO_TRADE_ONLY", "execution_enabled": False, "orders_placed": False,
                    "source": "gateio_public_spot", "source_reader": "global_market_data_reader_v1",
                    "source_symbol": gateio_spot_source_symbol(batch.candles[-1].symbol), "symbol_mapping_verified": verify_gateio_spot_symbol_mapping(batch.candles[-1].symbol, gateio_spot_source_symbol(batch.candles[-1].symbol)),
                    "execution_instrument_mapping_verified": False,
                    "input_batch_sha256": batch.response_sha256,
                    "latest_age_seconds": latest_age_seconds,
                }
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except Exception as exc:
                payload = {
                    "status": "blocked", "mode": "NO_TRADE_ONLY",
                    "error": "market_data_unavailable", "reason": type(exc).__name__,
                    "fail_closed": True, "execution_enabled": False, "orders_placed": False,
                    "symbol_mapping_verified": False, "execution_instrument_mapping_verified": False,
                }
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/precision-entry":
            try:
                from forward.global_market_data_reader_v1 import read_closed_candles
                from forward.precision_entry_engine_v1 import evaluate_precision_entry
                root = _market_data_root()
                feeds = {
                    tf: read_closed_candles(tf, root=root, min_bars=(50 if tf == "1m" else 200))
                    for tf in ("4h", "1h", "15m", "1m")
                }
                now_s = int(time.time())
                timeframe_payload = {}
                stale_timeframe_codes = []
                for tf, rows in feeds.items():
                    age_seconds = now_s - int(rows[-1]["close_time"])
                    max_age_seconds = MAX_CANDLE_AGE_SECONDS[tf]
                    if age_seconds < 0:
                        status = "FUTURE"
                        stale_timeframe_codes.append(f"FUTURE_CANDLE_{tf.upper()}")
                    elif age_seconds > max_age_seconds:
                        status = "STALE"
                        stale_timeframe_codes.append(f"STALE_CANDLE_{tf.upper()}")
                    else:
                        status = "VALIDATED"
                    timeframe_payload[tf] = {
                        "status": status,
                        "source": "gateio_public_spot",
                        "source_reader": "global_market_data_reader_v1",
                        "symbol": "BTC_USDT",
                        "timeframe": tf,
                        "input_batch_sha256": canonical_market_batch_sha256(rows),
                        "batch_candles": min(len(rows), 240),
                        "closed_candles": len(rows),
                        "latest_close_time": rows[-1]["close_time"],
                        "latest_age_seconds": age_seconds,
                        "max_age_seconds": max_age_seconds,
                    }
                if stale_timeframe_codes:
                    latest_1m = feeds["1m"][-1]
                    payload = {
                        "schema": "hes_precision_entry_status_v1",
                        "status": "BLOCKED",
                        "source": "gateio_public_spot",
                        "symbol": "BTC_USDT",
                        "timeframes": timeframe_payload,
                        "setup_timeframe": "15m",
                        "setup_decision": "NO_TRADE",
                        "final_policy_decision": "NO_TRADE",
                        "paper_setup_validated": False,
                        "paper_setup_reason": "STALE_MARKET_DATA",
                        "setup_validated_15m": False,
                        "confirmation_state": "UNCONFIRMED",
                        "risk_gate_state": "RISK_REJECTED",
                        "entry_timeframe": "1m",
                        "entry_state": "BLOCKED",
                        "reason_codes": stale_timeframe_codes,
                        "engine_evidence": {"freshness_gate": "BLOCKED"},
                        "engine_authority": "ADVISORY_ONLY_RISK_GATE_UNCHANGED",
                        "entry_context_status": "MISSING",
                        "latest_1m_close_time": latest_1m["close_time"],
                        "execution_enabled": False,
                        "orders_placed": False,
                        "authority": "ADVISORY_ONLY_RISK_GATE_UNCHANGED",
                    }
                    return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
                current_provenance = _current_chart_batch_provenance()
                for timeframe in ("15m", "1h", "4h"):
                    if canonical_market_batch_sha256(feeds[timeframe]) != current_provenance["timeframes"][timeframe]["input_batch_sha256"]:
                        raise ValueError("precision_chart_batch_mismatch:" + timeframe)
                chart_1m_batch, _ = _get_batch("BTCUSDT", "1m")
                if canonical_market_batch_sha256(feeds["1m"]) != chart_1m_batch.response_sha256:
                    raise ValueError("precision_chart_batch_mismatch:1m")
                strategy = read_strategy_v2_dashboard(current_market_data_provenance=current_provenance)
                gate = strategy.get("latest_gate_evidence", {})
                if not isinstance(gate, dict):
                    raise ValueError("strategy_gate_evidence_invalid")
                confirmation = gate.get("confirmation", {})
                risk = gate.get("risk", {})
                if not isinstance(confirmation, dict) or not isinstance(risk, dict):
                    raise ValueError("strategy_gate_stage_invalid")
                paper_setup = strategy.get("paper_setup", {})
                setup_valid = paper_setup.get("validated") is True
                direction = str(paper_setup.get("direction", "NONE")).upper() if setup_valid else "NONE"
                setup_decision = direction if setup_valid else "NO_TRADE"
                confirmation_state = confirmation.get("state", "UNKNOWN")
                risk_state = risk.get("state", "UNKNOWN")
                context = paper_setup.get("context")
                engine = evaluate_precision_entry(
                    setup_direction=direction,
                    candles_1m=feeds["1m"],
                    setup_validated_15m=setup_valid,
                    risk_gate_state=risk_state,
                    now_s=int(time.time()),
                    setup_context=context if isinstance(context, dict) else None,
                )
                if strategy.get("execution_enabled") is not False or strategy.get("orders_placed") is not False:
                    raise ValueError("execution_boundary_violation")
                latest_1m = feeds["1m"][-1]
                payload = {
                    "schema": "hes_precision_entry_status_v1",
                    "status": "BLOCKED" if engine["state"] == "BLOCKED" else engine["state"],
                    "source": "gateio_public_spot",
                    "symbol": "BTC_USDT",
                    "timeframes": timeframe_payload,
                    "setup_timeframe": "15m",
                    "setup_decision": setup_decision,
                    "final_policy_decision": strategy.get("decision", "NO_TRADE"),
                    "paper_setup_validated": setup_valid,
                    "paper_setup_reason": paper_setup.get("reason_code"),
                    "setup_validated_15m": setup_valid,
                    "confirmation_state": confirmation_state,
                    "risk_gate_state": risk_state,
                    "entry_timeframe": "1m",
                    "entry_state": engine["state"],
                    "reason_codes": list(engine["reason_codes"]),
                    "engine_evidence": engine["evidence"],
                    "engine_authority": engine["authority"],
                    "entry_context_status": "PRESENT" if isinstance(context, dict) else "MISSING",
                    "latest_1m_close_time": latest_1m["close_time"],
                    "execution_enabled": False,
                    "orders_placed": False,
                    "authority": "ADVISORY_ONLY_RISK_GATE_UNCHANGED",
                }
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except Exception as exc:
                payload = {
                    "schema": "hes_precision_entry_status_v1",
                    "status": "BLOCKED",
                    "error": "precision_entry_evidence_unavailable",
                    "reason": type(exc).__name__,
                    "reason_codes": ["MULTI_TIMEFRAME_EVIDENCE_UNAVAILABLE"],
                    "fail_closed": True,
                    "execution_enabled": False,
                    "orders_placed": False,
                    "authority": "ADVISORY_ONLY_RISK_GATE_UNCHANGED",
                }
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/journal":
            q = parse_qs(p.query)
            try:
                limit = int(q.get("limit", ["50"])[0])
                journal_path = os.environ.get(
                    "HES_TRADE_JOURNAL_PATH",
                    str(PROJECT_ROOT / "data" / "forward" / "trade_journal_v2.jsonl"),
                )
                payload = configured_decision_journal(journal_path=journal_path, limit=limit)
                payload.setdefault("execution_enabled", False)
                payload["orders_placed"] = False
                payload.setdefault("outcomes_inferred", False)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (JournalProjectionError, ValueError) as exc:
                payload = {
                    "schema": "hes.trade_journal_view.v1", "status": "BLOCKED",
                    "error": str(exc), "events": [], "count": 0,
                    "execution_enabled": False, "orders_placed": False, "outcomes_inferred": False,
                }
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/strategy-v2":
            try:
                current_provenance = _current_chart_batch_provenance()
                payload = read_strategy_v2_dashboard(current_market_data_provenance=current_provenance)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (StrategyV2DashboardError, ValueError) as exc:
                payload = {
                    "schema": "hes.strategy_v2_dashboard_view.v1", "status": "BLOCKED",
                    "decision": "NO_TRADE", "direction": "NONE", "reason": str(exc),
                    "source": "gateio_public_spot", "execution_enabled": False,
                    "orders_placed": False, "outcomes_inferred": False, "fail_closed": True,
                }
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/mother":
            try:
                current_provenance = _current_chart_batch_provenance()
                strategy_view = read_strategy_v2_dashboard(current_market_data_provenance=current_provenance)
                payload = read_mother_v2_dashboard(strategy_view=strategy_view)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (StrategyV2DashboardError, MotherV2DashboardError, ValueError) as exc:
                payload = {
                    "schema": "hes.mother_v2_dashboard_view.v1", "status": "BLOCKED_EVIDENCE",
                    "decision": "NO_TRADE", "reason_codes": [str(exc)], "stages": [],
                    "witness": {"verified": False, "reason_codes": ["MOTHER_EVIDENCE_UNVERIFIED"]},
                    "execution_authorized": False, "execution_enabled": False,
                    "orders_placed": False, "fail_closed": True,
                }
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/news":
            try:
                snapshot = _NEWS_MONITOR.read_snapshot(max_age_seconds=max(600, _NEWS_MONITOR_INTERVAL * 3))
                monitor = snapshot["monitor"]
                if monitor["status"] == "BLOCKED" or snapshot.get("brief") is None:
                    raise ValueError("news_monitor_blocked")
                return self._send(200, json.dumps(snapshot, separators=(",", ":")).encode(), "application/json")
            except Exception as exc:
                return self._send(503, json.dumps({
                    "status": "BLOCKED", "error": type(exc).__name__,
                    "fail_closed": True, "execution_enabled": False, "orders_placed": False,
                }, separators=(",", ":")).encode(), "application/json")
        # Retired V1 signal endpoint: never invoke the old decision engine or journal writer.
        if p.path == "/api/signal":
            return self._send(410, json.dumps({
                "error": "legacy_signal_route_retired", "status": "DEPRECATED",
                "decision": "NO_TRADE", "fail_closed": True,
                "execution_enabled": False, "orders_placed": False,
            }, separators=(",", ":")).encode(), "application/json")
        if p.path!="/api/candles": return self._send(404,b'{"error":"not_found"}',"application/json")
        q=parse_qs(p.query); symbol=q.get("symbol",["BTCUSDT"])[0]; interval=q.get("interval",["15m"])[0]
        if symbol not in SUPPORTED_SYMBOLS or interval not in SUPPORTED_INTERVALS or interval not in INTERVAL_MS:
            return self._send(400,b'{"error":"unsupported_symbol_or_interval"}',"application/json")
        try:
            # The exact same validated batch feeds the chart projection and feature pipeline.
            batch,feature_result=_get_batch(symbol,interval)
            now=datetime.now(timezone.utc); now_ms=int(now.timestamp()*1000); last=batch.candles[-1]
            age=(now_ms-last.close_time_ms)/1000
            payload={"status":"gaps_present" if batch.gaps else "ok",
                "source":"gateio_public_spot","source_reader":"global_market_data_reader_v1",
                "venue":batch.venue,"product":batch.product,
                "volume_semantics_contract":VOLUME_SEMANTICS_CONTRACT_VERSION,
                "trade_count_available":TRADE_COUNT_AVAILABLE,"taker_buy_flow_available":TAKER_BUY_FLOW_AVAILABLE,
                "symbol":batch.symbol,"source_symbol":gateio_spot_source_symbol(batch.symbol),"symbol_mapping_verified":verify_gateio_spot_symbol_mapping(batch.symbol,gateio_spot_source_symbol(batch.symbol)),
                "execution_instrument_mapping_verified":False,
                "interval":batch.interval,"endpoint_kind":batch.endpoint_kind,
                "fetched_at_ms":batch.fetched_at_ms,"input_batch_sha256":batch.response_sha256,
                "latest_age_seconds":age,"execution_enabled":False,"orders_placed":False,
                "feature_ready":feature_result.decision_ready,"feature_reason":feature_result.reason,
                "stream_status":_STREAM_STATE["status"],"stream_reason":_STREAM_STATE["reason"],
                "gaps":[{"expected_open_time_ms":g.expected_open_time_ms,
                    "next_observed_open_time_ms":g.next_observed_open_time_ms,
                    "missing_intervals":g.missing_intervals} for g in batch.gaps],
                "candles":[{"open_time":c.open_time_ms,"close_time":datetime.fromtimestamp(c.close_time_ms/1000,timezone.utc).isoformat(),
                    "open":str(c.open),"high":str(c.high),"low":str(c.low),"close":str(c.close),
                    "volume":str(c.volume),"quote_volume":str(c.quote_volume)} for c in batch.candles]}
            return self._send(200,json.dumps(payload,separators=(",",":")).encode(),"application/json")
        except Exception as exc:
            reason_code = str(exc) if str(exc) in {"latest_closed_candle_stale", "persisted_candle_gaps_present"} else type(exc).__name__
            return self._send(503,json.dumps({"error":"market_data_unavailable",
                "reason":type(exc).__name__,"reason_code":reason_code,"fail_closed":True,"execution_enabled":False,"orders_placed":False}).encode(),"application/json")
    def do_POST(self):
        path = urlparse(self.path).path
        allowed = {"/api/mother-chat/session", "/api/mother-chat", "/api/mother-chat/logout"}
        if path not in allowed:
            return self._send(405,b'{"error":"method_not_allowed","execution_enabled":false,"orders_placed":false}',"application/json")
        try:
            scheme = _MOTHER_CHAT_SECURITY.check_origin(self.headers)
            client = self.client_address[0] if self.client_address else "unknown"
            if path == "/api/mother-chat/session":
                _MOTHER_CHAT_SECURITY.check_rate_limit(client, "login", limit=5, window_seconds=600)
                payload = read_json_body(self)
                if set(payload) != {"token"}:
                    raise MotherChatError("CHAT_LOGIN_PAYLOAD_INVALID", 400)
                cookie = _MOTHER_CHAT_SECURITY.create_session_cookie(payload.get("token"), secure=(scheme == "https"))
                body = json.dumps({"status":"OK","session_expires_in":1800},separators=(",",":")).encode()
                return self._send(200,body,"application/json",[("Set-Cookie",cookie)])
            if path == "/api/mother-chat/logout":
                cookie = _MOTHER_CHAT_SECURITY.clear_session_cookie(secure=(scheme == "https"))
                body = b'{"status":"OK","execution_enabled":false,"orders_placed":false}'
                return self._send(200,body,"application/json",[("Set-Cookie",cookie)])
            _MOTHER_CHAT_SECURITY.check_rate_limit(client, "chat", limit=30, window_seconds=60)
            if not _MOTHER_CHAT_SECURITY.has_valid_session(self.headers):
                raise MotherChatError("CHAT_SESSION_REQUIRED", 401)
            payload = read_json_body(self)
            if set(payload) != {"message"}:
                raise MotherChatError("CHAT_MESSAGE_PAYLOAD_INVALID", 400)
            result = build_chat_response(payload.get("message"), _mother_chat_readers())
            body = json.dumps(result,separators=(",",":"),ensure_ascii=False).encode("utf-8")
            return self._send(200,body,"application/json")
        except MotherChatError as exc:
            body = json.dumps({
                "status":"BLOCKED","error":exc.code,
                "execution_enabled":False,"orders_placed":False,
            },separators=(",",":")).encode()
            return self._send(exc.http_status,body,"application/json")
        except Exception:
            body = b'{"status":"BLOCKED","error":"CHAT_REQUEST_FAILED","execution_enabled":false,"orders_placed":false}'
            return self._send(503,body,"application/json")
    def log_message(self,fmt,*args):
        if os.environ.get("HES_DASHBOARD_ACCESS_LOG")=="1": super().log_message(fmt,*args)

def main():
    # The legacy Binance stream is deliberately not started by the Gate.io chart path.
    # Gate.io candles are REST-refreshed; a matching Gate.io stream needs its own
    # source-identity/reconciliation tests before it can be enabled.
    _STREAM_STATE.update(status="disabled", reason="gateio_stream_not_enabled")
    host=os.environ.get("HES_DASHBOARD_HOST","127.0.0.1"); port=int(os.environ.get("HES_DASHBOARD_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    stop = Event()
    monitor_thread = Thread(target=_NEWS_MONITOR.run_forever, args=(stop,), name="hes-news-monitor", daemon=True)
    monitor_thread.start()
    print(f"HES read-only dashboard listening on http://{host}:{port}",flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        monitor_thread.join(timeout=5)
        server.server_close()

if __name__=="__main__": main()
