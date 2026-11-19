"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
import hashlib, json, os, time
from decimal import Decimal
from math import isfinite
from urllib.parse import parse_qs, urlparse
from forward.native_ohlcv_v1 import INTERVAL_MS, NativeCandle, NativeOHLCVBatch, validate_native_batch
from forward.global_market_data_reader_v1 import load_market_input, canonical_market_batch_sha256
from forward.native_ohlcv_gateio_v1 import (
    VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES, VOLUME_SEMANTICS_CONTRACT_VERSION,
    TRADE_COUNT_AVAILABLE, TAKER_BUY_FLOW_AVAILABLE, GATEIO_SPOT_SYMBOL_MAP, GateioSpotKlineSource,
    gateio_spot_source_symbol, verify_gateio_spot_symbol_mapping)
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.trade_journal_view_v1 import configured_decision_journal, JournalProjectionError
from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain
from core.market_intelligence.news_monitor import NewsMonitorV1
from web.strategy_v2_dashboard_view import read_strategy_v2_dashboard, StrategyV2DashboardError
from web.mother_runtime_dashboard_view import read_mother_runtime_dashboard, MotherRuntimeDashboardError
from web.mother_chat_v1 import MotherChatError, MotherChatSecurityV1, build_chat_response, read_json_body
from web.hoshyar_local_v1 import HoshyarConversationMemoryV1, HoshyarLocalAssistantV1, HoshyarLocalError, HoshyarLocalLLMV1
from web.hoshyar_project_memory_v1 import HoshyarProjectMemoryReaderV1
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream
from forward.universal_indicator_engine_v1 import build_snapshot as build_universal_indicator_snapshot, dashboard_payload as build_indicator_dashboard_payload, INDICATOR_REGISTRY

SUPPORTED_SYMBOLS = set(GATEIO_SPOT_SYMBOL_MAP)
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
    """Reuse persisted BTC candles and the shared native Gate.io adapter for explicitly mapped altcoins."""
    venue = "gateio"
    product = "spot"

    def fetch(self, *, symbol, interval="15m", limit=240, start_time_ms=None, end_time_ms=None, as_of_ms=None):
        if symbol not in SUPPORTED_SYMBOLS or interval not in SUPPORTED_INTERVALS:
            raise ValueError("unsupported persisted global-feed identity")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid persisted candle limit")
        if start_time_ms is not None or end_time_ms is not None or as_of_ms is not None:
            raise ValueError("persisted global feed does not support custom time windows")
        if symbol != CANONICAL_ANALYSIS_SYMBOL:
            return _NATIVE_GATEIO_SOURCE.fetch(
                symbol=symbol, interval=interval, limit=limit,
                start_time_ms=start_time_ms, end_time_ms=end_time_ms, as_of_ms=as_of_ms,
            )
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


_NATIVE_GATEIO_SOURCE = GateioSpotKlineSource()
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

def _source_reader_identity(batch):
    if batch.endpoint_kind == "global_market_data_reader_v1":
        return "global_market_data_reader_v1"
    if batch.endpoint_kind == "spot_candlesticks":
        return "native_ohlcv_gateio_v1"
    raise ValueError("unsupported_market_data_reader_identity")

def _indicator_series_payload(points, batch, period):
    # Validate complete indicator points against the chart's exact candle times.
    if type(period) is not int or period <= 0 or not isinstance(points, (tuple, list)):
        return None
    candles = batch.candles
    if len(candles) < period:
        return None
    expected_times = [c.open_time_ms // 1000 for c in candles[period - 1:]]
    if len(points) != len(expected_times):
        return None
    payload = []
    for point, expected_time in zip(points, expected_times):
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            return None
        timestamp, value = point
        if type(timestamp) is not int or timestamp != expected_time:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not isfinite(value) or value <= 0:
            return None
        payload.append({"time": timestamp, "value": float(value)})
    return payload


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
<title>HES Trade Agent</title><link rel="icon" href="/static/hes-mark.svg" type="image/svg+xml"><link rel="stylesheet" href="/static/dashboard.css"><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><a class="skip-link" href="#main-content">Skip to dashboard content</a><main id="main-content" tabindex="-1"><header><div class="brand-lockup"><img class="brand-mark" src="/static/hes-mark.svg" alt="" aria-hidden="true"><div><h1 class="brand">HES Trade Agent</h1></div></div><div class="header-actions"><label class="language-control" for="languageSelect"><span class="sr-only">Language</span><select id="languageSelect" aria-label="Dashboard language"><option value="en">English</option><option value="fa">فارسی</option><option value="de">Deutsch</option><option value="fr">Français</option></select></label><span class="pill" aria-label="Execution disabled">NO TRADE<span class="sr-only">HOLD / NO_TRADE_ONLY</span></span></div></header>
<nav class="section-nav" aria-label="Dashboard sections"><a href="#marketPanel">Market</a><a href="#precisionEntryPanel">Entry</a><a href="#strategyV2Panel">Strategy</a><a href="#motherChatPanel">Command Center</a><a class="sr-only" href="#motherChatPanel">HES Command Center</a><div class="sr-only"><a href="#technicalIntelligencePanel">Indicators</a><a href="#motherPanel">Mother</a><a href="#newsRadarPanel">News</a><a href="#safetyPanel">Safety</a><a href="#journalPanel">Journal</a><a href="#documentationPanel">Documentation</a></div></nav>
<section class="panel" id="marketPanel" aria-labelledby="marketTitle"><h2 class="panel-title" id="marketTitle">Market</h2><div class="toolbar"><label>Pair <select id="symbol"><option value="BTCUSDT">BTC / USDT</option><option value="ETHUSDT">ETH / USDT</option><option value="SOLUSDT">SOL / USDT</option></select></label><label>TF <select id="interval"><option>15m</option><option>1m</option><option>1h</option><option>4h</option></select></label><button id="refresh">Refresh</button><span class="muted" id="source">Gate.io · validated</span><span class="sr-only">Validated Gate.io Public Spot feed. Strategy/Mother decision panels remain BTC-canonical</span></div>
<div class="metrics"><div class="metric"><small>Last close</small><strong id="price" data-no-translate>—</strong></div><div class="metric"><small>UTC</small><strong id="stamp" data-no-translate class="stamp">—</strong></div><div class="metric"><small>Volume</small><strong id="volume" data-no-translate>—</strong></div><div class="metric"><small>Candles</small><strong id="count" data-no-translate>—</strong></div></div>
<div class="panel chart-panel">
<div class="chart-indicator-toolbar" role="group" aria-label="Chart overlays">
<span class="chart-overlays-label">Overlays</span>
<label for="showEma"><input id="showEma" type="checkbox" checked><span class="indicator-swatch ema"></span><span>EMA (20)</span></label>
<label for="showVwap"><input id="showVwap" type="checkbox" checked><span class="indicator-swatch vwap"></span><span>VWAP (20)</span></label>
<span id="chartIndicatorStatus" class="muted" role="status" aria-live="polite"></span>
</div>
<div id="chart" role="img" aria-label="Candlestick chart with EMA and VWAP overlays"></div></div>
<div class="panel indicator-panel" aria-labelledby="indicatorTitle"><h3 class="panel-title" id="indicatorTitle">Indicators</h3><div class="metrics" id="indicatorMetrics" role="group" aria-label="Descriptive indicators"><div class="metric"><small>EMA (20)</small><strong id="indicatorEma" data-no-translate>—</strong></div><div class="metric"><small>VWAP (20)</small><strong id="indicatorVwap" data-no-translate>—</strong></div><div class="metric"><small>ATR</small><strong id="indicatorAtr" data-no-translate>—</strong></div><div class="metric"><small>Realized volatility</small><strong id="indicatorVolatility" data-no-translate>—</strong></div><div class="metric"><small>Volume ratio</small><strong id="indicatorVolumeRatio" data-no-translate>—</strong></div><div class="metric"><small>Market regime</small><strong id="indicatorRegime" data-no-translate>—</strong></div></div><p class="muted" id="indicatorStatus" data-no-translate role="status" aria-live="polite"></p><p class="muted">Descriptive only</p></div>
<div id="message" role="status" aria-live="polite" aria-atomic="true"></div></section>
<section class="panel" id="precisionEntryPanel" aria-labelledby="precisionEntryTitle"><h2 class="panel-title" id="precisionEntryTitle">Entry</h2><div class="metrics"><div class="metric"><small>4H data</small><strong id="pe4h" data-no-translate>Checking…</strong></div><div class="metric"><small>1H data</small><strong id="pe1h" data-no-translate>Checking…</strong></div><div class="metric"><small>15M setup gate</small><strong id="pe15m" data-no-translate>Checking…</strong></div><div class="metric"><small>1M feed</small><strong id="pe1m" data-no-translate>Checking…</strong></div><div class="metric"><small>Precision Entry</small><strong id="peState" data-no-translate>BLOCKED</strong></div><div class="metric"><small>Risk Gate</small><strong id="peRisk" data-no-translate>UNVERIFIED</strong></div></div><p class="muted" id="peReasons" data-no-translate role="status" aria-live="polite"></p><div class="gate"><strong>15m setup · 1m entry · Risk Gate</strong><p class="muted">Read-only · execution disabled</p></div></section>
<section class="panel" id="technicalIntelligencePanel" aria-labelledby="technicalIntelligenceTitle">
<h2 class="panel-title" id="technicalIntelligenceTitle">Indicators</h2><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body">
<p class="muted">Read-only research · Gate.io Public Spot. The initial 15m/1m/1h/4h timeframe-role profile is validated for BTC only; ETH/SOL remain descriptive until their own timeframe profiles pass validation. Regime evidence share is not a predictive probability.</p>
<div class="metrics">
<div class="metric"><small>Engine status</small><strong id="technicalStatus" data-no-translate>Checking…</strong></div>
<div class="metric"><small>Regime alignment</small><strong id="technicalConsensus" data-no-translate>UNKNOWN</strong></div>
<div class="metric"><small>Source</small><strong id="technicalSource" data-no-translate>Gate.io</strong></div>
<div class="metric"><small>Safety</small><strong id="technicalSafety" data-no-translate>READ ONLY</strong></div>
</div>
<div class="metrics" id="technicalRegimeMetrics" aria-live="polite"><div class="metric"><small>4H</small><strong>—</strong></div><div class="metric"><small>1H</small><strong>—</strong></div><div class="metric"><small>15M</small><strong>—</strong></div><div class="metric"><small>1M</small><strong>—</strong></div></div>
<div class="toolbar"><label for="technicalTimeframe">Indicator detail timeframe</label><select id="technicalTimeframe"><option value="15m" selected>15m</option><option value="4h">4h</option><option value="1h">1h</option><option value="1m">1m</option></select><button id="technicalRefresh" type="button">Refresh indicators</button></div>
<p class="muted" id="technicalProvenance">Waiting for provenance-bound indicator evidence…</p><p class="muted" id="technicalProfile">Waiting for regime-adaptive indicator profile…</p>
<div class="journal-scroll"><table class="journal-table"><caption class="sr-only">Read-only technical indicator values and availability</caption><thead><tr><th>Family</th><th>Indicator</th><th>Value</th><th>Status / reason</th></tr></thead><tbody id="technicalIndicatorRows"><tr><td colspan="4">No indicator evidence loaded.</td></tr></tbody></table></div>
<div class="gate"><strong>Research-only · no signal or policy authority</strong><p class="muted">Indicators are grouped to avoid double-counting correlated evidence. Missing volume semantics disables volume-derived indicators only. This panel cannot generate signals, alter strategy thresholds, bypass Risk Gate, write journals, or place orders.</p></div>
</div></details></section>
<section class="panel" id="strategyV2Panel" aria-labelledby="strategyV2Title"><h2 class="panel-title" id="strategyV2Title">Strategy</h2><div class="metrics"><div class="metric"><small>Canonical decision</small><strong id="v2Decision" data-no-translate>NO_TRADE</strong></div><div class="metric"><small>Evidence status</small><strong id="v2Status" data-no-translate role="status" aria-live="polite">Checking report…</strong></div><div class="metric"><small>Market regime</small><strong id="v2Regime" data-no-translate>UNKNOWN</strong></div><div class="metric"><small>Policy version</small><strong id="v2Version" data-no-translate>—</strong></div><div class="metric"><small>Paper outcomes</small><strong id="v2Outcomes" data-no-translate>—</strong></div><div class="metric"><small>Decision journal</small><strong id="v2Journal" data-no-translate>—</strong></div></div><p class="muted" id="v2Reasons" data-no-translate></p><div class="gate"><strong>Gate.io · read-only</strong><p class="muted" id="v2Evidence" data-no-translate>No orders</p></div></section>
<section class="panel" id="motherPanel" aria-labelledby="motherTitle"><h2 class="panel-title" id="motherTitle">Mother<span class="sr-only">Mother Orchestrator · canonical V2 evidence chain</span></h2><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body"><div class="metrics"><div class="metric"><small>Orchestration</small><strong id="motherStatus" data-no-translate role="status" aria-live="polite">BLOCKED</strong></div><div class="metric"><small>Independent witness</small><strong id="motherWitness" data-no-translate>NOT VERIFIED</strong></div><div class="metric"><small>Trace / audit</small><strong id="motherTrace" data-no-translate>—</strong></div></div><p class="muted" id="motherReasons" data-no-translate>Waiting for live Gate.io data and runtime specialist evaluation…</p><p class="muted" id="motherPaperGate" data-no-translate>Paper simulation gate: awaiting recovery and activation evidence…</p><ul id="motherStages" data-no-translate><li class="muted">No verified orchestration stages.</li></ul><div class="gate"><strong>Observation only · execution disabled</strong><p class="muted" id="motherEvidence" data-no-translate>Mother runs the seven HES specialist evaluators against the current validated Gate.io snapshot. It uses the shared persisted data path and cannot authorize orders.</p></div></div></details></section>
<section class="panel" id="motherChatPanel" aria-labelledby="motherChatTitle"><h2 class="panel-title" id="motherChatTitle">Command Center<span class="sr-only">HES Trade AI · Private local AI</span></h2><p class="muted">Deterministic, multilingual, read-only access to the existing Mother specialists and evidence. No paid API or external LLM is used; the optional local model remains disabled unless separately accepted. Mother and Risk remain the only decision authorities. No account access, order tools, policy changes or journal writes.</p><div id="motherChatLogin"><form id="motherChatLoginForm"><label for="motherChatToken">Local access token</label><input id="motherChatToken" type="password" autocomplete="current-password" maxlength="256" required><button id="motherChatUnlock" type="submit">Unlock HES Command Center</button><p class="muted" id="motherChatLoginStatus" role="status" aria-live="polite">Access is disabled until the operator configures the local token file.</p></form></div><div id="motherChatWorkspace" hidden><p class="muted" id="motherChatMemoryStatus" role="status" aria-live="polite">Local model is disabled; deterministic Mother chat remains active.</p><div id="motherChatMessages" class="mother-chat-messages" role="log" aria-live="polite" aria-relevant="additions text"><p class="muted">Ask about Mother status, specialist stages, a decision, the market, journal, news or diagnostics.</p></div><form id="motherChatForm"><label for="motherChatLanguage">Response language</label><select id="motherChatLanguage" name="language" aria-label="Response language" data-no-translate><option value="auto">Auto · match message</option><option value="fa">فارسی</option><option value="en">English</option><option value="de">Deutsch</option><option value="fr">Français</option></select><label for="motherChatInput">Message HES Trade AI / Mother</label><textarea id="motherChatInput" rows="2" maxlength="1000" required placeholder="مثلاً: چرا تصمیم مادر عدم ترید است؟"></textarea><div class="mother-chat-actions"><button id="motherChatSend" type="submit">Send</button><button id="motherChatClearMemory" type="button" class="secondary" disabled>Clear local memory</button><button id="motherChatLogout" type="button" class="secondary">Lock</button></div></form></div><div class="gate"><strong>Safety boundary</strong><p class="muted">Mother explains recorded evidence; it does not create a new signal. Gate.io Public Spot BTC_USDT remains the sole analysis source. Execution, account access and all write actions remain disabled.</p></div></section>
<section class="panel" id="newsRadarPanel" aria-labelledby="newsTitle"><h2 class="panel-title" id="newsTitle">News Radar · read-only evidence</h2><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body"><div class="metrics"><div class="metric"><small>Monitor</small><strong id="newsStatus" data-no-translate role="status" aria-live="polite">BLOCKED</strong></div><div class="metric"><small>Qualified coverage</small><strong id="newsCoverage" data-no-translate>UNKNOWN</strong></div><div class="metric"><small>Sources OK / empty / failed</small><strong id="newsSources" data-no-translate>0 / 0 / 0</strong></div><div class="metric"><small>International / domestic / venue</small><strong id="newsScopes" data-no-translate>0 / 0 / 0</strong></div><div class="metric"><small>Fresh / aging / stale / future / empty / failed / unknown</small><strong id="newsFreshness" data-no-translate>0 / 0 / 0 / 0 / 0 / 0 / 0</strong></div><div class="metric"><small>Last poll (UTC)</small><strong id="newsLastPoll" data-no-translate>—</strong></div></div><p class="muted" id="newsSummary" data-no-translate>Waiting for verified news evidence…</p><p class="muted" id="newsFlags" data-no-translate>News does not originate trade direction or authorize execution.</p><ul id="newsItems" data-no-translate><li class="muted">No verified headlines loaded.</li></ul><h3>Per-source health and freshness</h3><ul id="newsSourceDetails" data-no-translate><li class="muted">No per-source health loaded.</li></ul><div class="gate"><strong>Context only · no trade authorization</strong><p class="muted">Gate.io remains the sole live market-data source. Gate.io announcements are venue-operational news only; candles, indicators and chart data never come from news feeds. News coverage is explicitly partial where shown.</p></div></div></details></section>
<section class="panel" id="safetyPanel" aria-labelledby="safetyTitle"><h2 class="panel-title" id="safetyTitle">Safety</h2><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body"><div class="gate"><strong>Execution: disabled</strong><p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></div></details></section>
<section class="panel" id="documentationPanel" aria-labelledby="documentationTitle" data-no-translate><div class="toolbar documentation-heading"><div><h2 class="panel-title" id="documentationTitle">Documentation</h2><p class="muted" id="documentationIntro">Project DNA, architecture, roadmap and operational knowledge in four languages.</p></div><span class="pill" id="documentationSafety">READ ONLY</span></div><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body"><div class="documentation-controls"><label for="documentationSearch" id="documentationSearchLabel">Search documentation</label><input id="documentationSearch" type="search" maxlength="120" autocomplete="off" placeholder="Search titles and content"><label for="documentationCategory" id="documentationCategoryLabel">Category</label><select id="documentationCategory"><option value="">All categories</option></select><span class="muted" id="documentationStatus" role="status" aria-live="polite">Loading documentation…</span></div><div class="documentation-layout"><nav class="documentation-index" id="documentationIndex" aria-label="Documentation pages"><p class="muted">Loading…</p></nav><article class="documentation-article" id="documentationArticle" aria-live="polite"><p class="muted">Select a document.</p></article></div><div class="documentation-sources"><h3 id="documentationSourcesTitle">Source register</h3><ul id="documentationSources"></ul></div><p class="muted documentation-disclaimer" id="documentationDisclaimer">Reference material only. This section cannot change strategy, risk policy, journals or orders.</p></div></details></section>
<section class="panel" id="journalPanel" aria-labelledby="journalTitle"><div class="toolbar"><div><h2 class="panel-title" id="journalTitle">Journal<span class="sr-only">Trade Journal · Decision & Learning Evidence</span></h2><div class="muted">Immutable forward decisions only. Executed trades and realized outcomes are not inferred from a signal.</div></div><button id="journalRefresh" type="button">Refresh</button></div><details class="panel-disclosure"><summary class="panel-disclosure-summary" aria-label="Toggle section details" title="Toggle section details"><span class="sr-only">Toggle section details</span></summary><div class="panel-disclosure-body"><p class="muted" id="journalStatus" role="status" aria-live="polite" aria-atomic="true">Loading journal…</p><div class="journal-scroll"><table class="journal-table"><caption class="sr-only">Latest immutable forward decision events and their evidence references</caption><thead><tr><th scope="col">Time (UTC)</th><th scope="col">Market</th><th scope="col">Decision</th><th scope="col">Strategy family</th><th scope="col">Gate / reason</th><th scope="col">Outcome</th><th scope="col">Evidence</th></tr></thead><tbody id="journalRows" data-no-translate><tr><td colspan="7" class="muted">No journal entries loaded.</td></tr></tbody></table></div></div></details></section>
<div class="footer"><span>Charts powered by</span> <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. <span>Copyright (c) 2025 TradingView, Inc.</span> <span>BTC reads the validated persisted Gate.io candle feed; explicitly mapped ETH/SOL pairs reuse the shared native Gate.io Spot adapter. Chart and indicator calculations share the exact same batch and SHA-256 provenance. This is a single public venue source, not a cross-venue consolidated index. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Base and quote volume fields follow Gate.io's documented candlestick schema and are shown unchanged; trade count and taker-buy flow are unavailable. If the source is unavailable or stale, the chart fails closed.</span><span class="copyright" lang="en" dir="ltr" data-no-translate><span class="brand-footer-name">HES Trade Agent</span><span class="copyright-notice">Copyright © HES Trade Agent. All rights reserved.</span><span class="owner-name">SEYED HESAMEDDIN BEHESHTI SHIRAZI</span><span class="owner-role">Designer &amp; Owner</span></span></div></main>
<link rel="stylesheet" href="/static/documentation.css"><script src="/static/dashboard.js" defer></script><script src="/static/documentation.js" defer></script></body></html>'''



_MOTHER_CHAT_SECURITY = MotherChatSecurityV1()
_PROJECT_MEMORY_READER = HoshyarProjectMemoryReaderV1(PROJECT_ROOT)
_HOSHYAR_LOCAL_ASSISTANT = None
if os.environ.get("HES_HOSHYAR_LOCAL_LLM_ENABLED", "0") == "1":
    try:
        _HOSHYAR_LOCAL_ASSISTANT = HoshyarLocalAssistantV1(
            HoshyarLocalLLMV1(),
            HoshyarConversationMemoryV1(os.environ.get("HES_HOSHYAR_MEMORY_DB", "/var/lib/hes-news-monitor/hoshyar-memory.sqlite3")),
        )
    except HoshyarLocalError:
        _HOSHYAR_LOCAL_ASSISTANT = None


def _mother_chat_core_evidence():
    # Mother computes from the current shared Gate.io candle ledger on every
    # request. The chat receives a live proposal summary, never a saved report.
    mother = read_mother_runtime_dashboard(data_root=_market_data_root())
    proposal = mother.get("strategy_proposal") or {}
    strategy = {
        "status": "LIVE_RUNTIME" if mother.get("runtime_mode") == "LIVE_DATA_RUNTIME_SPECIALISTS" else "BLOCKED",
        "decision": proposal.get("decision", "NO_TRADE"),
        "market_regime": mother.get("market_regime", "UNKNOWN"),
        "snapshot_sha256": mother.get("snapshot_sha256"),
        "quality_score": proposal.get("quality_score"),
        "reason_codes": proposal.get("reason_codes", []),
        "execution_enabled": False,
        "orders_placed": False,
    }
    return strategy, mother


def _mother_chat_journal_evidence():
    journal_path = os.environ.get(
        "HES_TRADE_JOURNAL_PATH",
        str(PROJECT_ROOT / "data" / "forward" / "trade_journal_v2.jsonl"),
    )
    return configured_decision_journal(journal_path=journal_path, limit=20)


def _mother_chat_news_evidence():
    return _NEWS_MONITOR.read_snapshot(max_age_seconds=max(600, _NEWS_MONITOR_INTERVAL * 3))


def _mother_chat_readers(message: str = ""):
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

    def specialist_reader():
        strategy, mother = _mother_chat_core_evidence()
        return {
            "strategy": strategy, "mother": mother,
            "trace_id": mother.get("trace_id"),
            "evidence_refs": [x for x in (
                mother.get("trace_id"), mother.get("audit_sha256"),
                strategy.get("report_sha256"), mother.get("journal_event_sha256"),
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
            components["Mother orchestrator"] = {"status": mother.get("status", "UNKNOWN")}
            witness = mother.get("witness", {})
            witness_ok = isinstance(witness, dict) and witness.get("verified") is True
            components["Mother witness"] = {"status": "VERIFIED" if witness_ok else "BLOCKED"}
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
        "SPECIALIST_REVIEW": specialist_reader,
        "MARKET_REVIEW": market_reader,
        "JOURNAL_REVIEW": journal_reader,
        "NEWS_CONTEXT": news_reader,
        "DIAGNOSE": diagnose_reader,
        "PROJECT_MEMORY": lambda: _PROJECT_MEMORY_READER.search(message),
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
        if p.path == "/api/mother-chat/history":
            try:
                client = self.client_address[0] if self.client_address else "unknown"
                _MOTHER_CHAT_SECURITY.check_rate_limit(client, "history", limit=60, window_seconds=60)
                if not _MOTHER_CHAT_SECURITY.has_valid_session(self.headers):
                    raise MotherChatError("CHAT_SESSION_REQUIRED", 401)
                messages = _HOSHYAR_LOCAL_ASSISTANT.read_history() if _HOSHYAR_LOCAL_ASSISTANT is not None else []
                body = json.dumps({"messages": messages, "local_llm_enabled": _HOSHYAR_LOCAL_ASSISTANT is not None, "conversation_memory_enabled": _HOSHYAR_LOCAL_ASSISTANT is not None, "execution_enabled": False, "orders_placed": False}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json")
            except MotherChatError as exc:
                body = json.dumps({"error": exc.code}, separators=(",", ":")).encode()
                return self._send(exc.http_status, body, "application/json")
            except HoshyarLocalError:
                return self._send(503, b'{"error":"HOSHYAR_MEMORY_UNAVAILABLE"}', "application/json")
        if p.path == "/api/documentation":
            requested = parse_qs(p.query).get("lang", ["en"])[0]
            if requested not in {"fa", "en", "de", "fr"}:
                return self._send(400, b'{"error":"unsupported_documentation_language"}', "application/json")
            catalog_path = Path(__file__).resolve().parents[1] / "docs" / "documentation" / "catalog.v1.json"
            try:
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                if catalog.get("schema") != "hes_documentation_catalog_v1":
                    raise ValueError("documentation_schema_invalid")
                if catalog.get("safety") != {"read_only": True, "execution_enabled": False, "orders_placed": False, "policy_mutation": False}:
                    raise ValueError("documentation_safety_contract_invalid")
                pages = catalog.get("locales", {}).get(requested)
                if not isinstance(pages, list) or len(pages) < 10:
                    raise ValueError("documentation_locale_incomplete")
                if any(not isinstance(page, dict) or not page.get("id") or not page.get("title") or not page.get("sections") for page in pages):
                    raise ValueError("documentation_page_invalid")
                payload = {
                    "schema": "hes.documentation_response.v1",
                    "version": catalog["version"],
                    "updated_at": catalog["updated_at"],
                    "language": requested,
                    "pages": pages,
                    "ui": catalog.get("ui", {}).get(requested, {}),
                    "source_register": catalog.get("source_register", []),
                    "editorial_review": catalog.get("editorial_review", {}),
                    "safety": catalog["safety"],
                }
                body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json")
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                return self._send(503, b'{"error":"documentation_unavailable","fail_closed":true}', "application/json")
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
            "/static/documentation.js": ("documentation.js", "text/javascript; charset=utf-8"),
            "/static/documentation.css": ("documentation.css", "text/css; charset=utf-8"),
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
                payload = read_mother_runtime_dashboard(data_root=_market_data_root())
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (MotherRuntimeDashboardError, ValueError) as exc:
                payload = {
                    "schema": "hes.mother_runtime_dashboard.v1",
                    "runtime_mode": "BLOCKED",
                    "status": "BLOCKED_EVIDENCE",
                    "decision": "NO_TRADE",
                    "reason_codes": [str(exc)],
                    "registered_specialists": [],
                    "executed_specialists": [],
                    "stages": [],
                    "witness": {"verified": False, "reason_codes": ["MOTHER_RUNTIME_EVIDENCE_UNVERIFIED"]},
                    "execution_authorized": False,
                    "execution_enabled": False,
                    "orders_placed": False,
                    "journal_write": False,
                    "outcomes_inferred": False,
                    "fail_closed": True,
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
                    "schema": "hes.api_error.v1",
                    "status": "BLOCKED", "error": type(exc).__name__,
                    "fail_closed": True, "execution_enabled": False, "orders_placed": False,
                }, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/technical-intelligence":
            q = parse_qs(p.query)
            symbol = q.get("symbol", ["BTCUSDT"])[0]
            if symbol not in SUPPORTED_SYMBOLS:
                return self._send(400, b'{"error":"unsupported_symbol","fail_closed":true,"execution_enabled":false,"orders_placed":false}', "application/json")
            timeframes = {}
            failures = []
            for tf in ("4h", "1h", "15m", "1m"):
                try:
                    batch, _ = _get_batch(symbol, tf)
                    rows = [{
                        "timestamp": c.open_time_ms // 1000, "open": c.open, "high": c.high,
                        "low": c.low, "close": c.close, "volume": c.volume,
                        "quote_volume": c.quote_volume, "closed": c.closed,
                    } for c in batch.candles]
                    snapshot = build_universal_indicator_snapshot(
                        rows, venue=batch.venue, market=batch.product,
                        symbol=batch.symbol, timeframe=tf,
                        volume_semantics_qualified=VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES,
                    )
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    age = max(0, int((now_ms - batch.candles[-1].close_time_ms) / 1000))
                    timeframes[tf] = build_indicator_dashboard_payload(
                        snapshot, source="gateio_public_spot",
                        input_sha256=batch.response_sha256, freshness_seconds=age,
                    )
                    timeframes[tf]["source_reader"] = _source_reader_identity(batch)
                except Exception as exc:
                    failures.append(tf + ":" + type(exc).__name__)
                    timeframes[tf] = {
                        "status": "BLOCKED", "reason": type(exc).__name__,
                        "market_identity": {"venue":"gateio","market":"spot","symbol":gateio_spot_source_symbol(symbol),"canonical_symbol":symbol,"timeframe":tf},
                        "controls": {"decision_authority":False,"signal_generation_enabled":False,
                                     "risk_gate_bypass":False,"execution_enabled":False,
                                     "orders_placed":False,"journal_write":False,"policy_mutation":False},
                    }
            regimes = {tf: item.get("regime", {}).get("label", "UNKNOWN") for tf, item in timeframes.items()}
            directional = {x for x in regimes.values() if x in ("BULLISH", "BEARISH")}
            consensus = (next(iter(directional)) if len(directional) == 1 and all(x in directional for x in regimes.values())
                         else "MIXED" if directional else "NO_DIRECTIONAL_CONSENSUS")
            ready = not failures and all(item.get("status") == "READ_ONLY_RESEARCH" for item in timeframes.values())
            btc_roles = symbol == CANONICAL_ANALYSIS_SYMBOL
            first_batch = next((x for x in timeframes.values() if x.get("status") == "READ_ONLY_RESEARCH"), None)
            source_reader = first_batch.get("source_reader") if first_batch else ("global_market_data_reader_v1" if btc_roles else "native_ohlcv_gateio_v1")
            payload = {
                "schema":"hes.universal_indicator_dashboard_bundle.v1",
                "status":"VERIFIED" if ready else "PARTIAL",
                "source":"gateio_public_spot", "source_reader":source_reader,
                "symbol":gateio_spot_source_symbol(symbol), "canonical_symbol":symbol,
                "setup_authority_timeframe":"15m" if btc_roles else None,
                "precision_refinement_timeframe":"1m" if btc_roles else None,
                "context_timeframes":["1h","4h"] if btc_roles else [],
                "timeframe_roles":({"4h":"HIGHER_TIMEFRAME_CONTEXT","1h":"HIGHER_TIMEFRAME_CONTEXT","15m":"SETUP_AUTHORITY","1m":"PRECISION_REFINEMENT"} if btc_roles else {}),
                "timeframe_roles_status":"INITIAL_BTC_PROFILE" if btc_roles else "DESCRIPTIVE_ONLY_NOT_YET_VALIDATED_FOR_SYMBOL",
                "regime_consensus":consensus,
                "timeframes":timeframes, "indicator_registry":INDICATOR_REGISTRY,
                "failure_codes":failures,
                "controls":{"decision_authority":False,"signal_generation_enabled":False,
                            "risk_gate_bypass":False,"execution_enabled":False,
                            "orders_placed":False,"journal_write":False,"policy_mutation":False},
                "disclaimer":"Research-only descriptive features. Regime evidence share is not a probability, trade signal, strategy approval, or execution instruction."
            }
            return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")


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
            indicator_snapshot = getattr(feature_result, "snapshot", None)
            feature_quality = getattr(feature_result, "quality", None)
            feature_batch_sha256 = getattr(feature_result, "source_response_sha256", None)
            indicator_provenance_ok = feature_batch_sha256 == batch.response_sha256
            indicator_quality_ok = getattr(feature_quality, "passed", False) is True
            ema_series_payload = _indicator_series_payload(
                getattr(feature_result, "ema_series", ()), batch, _FEATURES.ema_period
            )
            vwap_series_payload = _indicator_series_payload(
                getattr(feature_result, "vwap_series", ()), batch, _FEATURES.vwap_period
            )
            indicator_series_ok = ema_series_payload is not None and vwap_series_payload is not None
            feature_ready = getattr(feature_result, "decision_ready", False) is True
            indicators_ready = (
                feature_ready
                and indicator_snapshot is not None
                and indicator_provenance_ok
                and indicator_quality_ok
                and indicator_series_ok
            )
            indicator_reason = (
                None if indicators_ready else
                "FEATURE_BATCH_PROVENANCE_MISMATCH" if not indicator_provenance_ok else
                getattr(feature_result, "reason", "INDICATOR_SNAPSHOT_UNAVAILABLE")
                if not (feature_ready and indicator_snapshot is not None and indicator_quality_ok) else
                "INDICATOR_SERIES_INVALID"
            )
            indicators = {
                "schema": "hes_native_ohlcv_indicator_snapshot_v1",
                "status": "READY" if indicators_ready else "BLOCKED",
                "source": "gateio_public_spot",
                "source_reader": _source_reader_identity(batch),
                "venue": batch.venue,
                "product": batch.product,
                "symbol": batch.symbol,
                "interval": batch.interval,
                "input_batch_sha256": batch.response_sha256,
                "feature_batch_sha256": feature_batch_sha256,
                "series_schema": "hes_native_ohlcv_indicator_series_v1",
                "ema_period": _FEATURES.ema_period,
                "vwap_period": _FEATURES.vwap_period,
                "ema_series": ema_series_payload if indicators_ready else [],
                "vwap_series": vwap_series_payload if indicators_ready else [],
                "ema": indicator_snapshot.ema if indicators_ready else None,
                "vwap": indicator_snapshot.vwap if indicators_ready else None,
                "average_true_range": indicator_snapshot.average_true_range if indicators_ready else None,
                "realized_volatility": indicator_snapshot.realized_volatility if indicators_ready else None,
                "volume_ratio": indicator_snapshot.volume_ratio if indicators_ready else None,
                "regime": indicator_snapshot.regime if indicators_ready else None,
                "quality_passed": indicator_quality_ok,
                "quality_violations": list(getattr(feature_quality, "violations", ()) or ()),
                "decision_ready": indicators_ready,
                "reason": indicator_reason,
                "execution_enabled": False,
                "orders_placed": False,
            }
            payload={"schema":"hes.market_candles_view.v1","status":"gaps_present" if batch.gaps else "ok",
                "source":"gateio_public_spot","source_reader":_source_reader_identity(batch),
                "venue":batch.venue,"product":batch.product,
                "volume_semantics_contract":VOLUME_SEMANTICS_CONTRACT_VERSION,
                "trade_count_available":TRADE_COUNT_AVAILABLE,"taker_buy_flow_available":TAKER_BUY_FLOW_AVAILABLE,
                "symbol":batch.symbol,"source_symbol":gateio_spot_source_symbol(batch.symbol),"symbol_mapping_verified":verify_gateio_spot_symbol_mapping(batch.symbol,gateio_spot_source_symbol(batch.symbol)),
                "execution_instrument_mapping_verified":False,
                "interval":batch.interval,"endpoint_kind":batch.endpoint_kind,
                "fetched_at_ms":batch.fetched_at_ms,"input_batch_sha256":batch.response_sha256,
                "latest_age_seconds":age,"execution_enabled":False,"orders_placed":False,
                "feature_ready":indicators_ready,"feature_reason":indicator_reason,
                "indicators":indicators,
                "stream_status":_STREAM_STATE["status"] if symbol == CANONICAL_ANALYSIS_SYMBOL else "disabled",
                "stream_reason":_STREAM_STATE["reason"] if symbol == CANONICAL_ANALYSIS_SYMBOL else "REST_ONLY_FOR_MAPPED_ALTCOIN",
                "gaps":[{"expected_open_time_ms":g.expected_open_time_ms,
                    "next_observed_open_time_ms":g.next_observed_open_time_ms,
                    "missing_intervals":g.missing_intervals} for g in batch.gaps],
                "candles":[{"open_time":c.open_time_ms,"close_time":datetime.fromtimestamp(c.close_time_ms/1000,timezone.utc).isoformat(),
                    "open":str(c.open),"high":str(c.high),"low":str(c.low),"close":str(c.close),
                    "volume":str(c.volume),"quote_volume":str(c.quote_volume)} for c in batch.candles]}
            return self._send(200,json.dumps(payload,separators=(",",":")).encode(),"application/json")
        except Exception as exc:
            reason_code = str(exc) if str(exc) in {"latest_closed_candle_stale", "persisted_candle_gaps_present"} else type(exc).__name__
            return self._send(503,json.dumps({"schema":"hes.market_candles_view.v1","error":"market_data_unavailable",
                "reason":type(exc).__name__,"reason_code":reason_code,"fail_closed":True,"execution_enabled":False,"orders_placed":False}).encode(),"application/json")
    def do_POST(self):
        path = urlparse(self.path).path
        allowed = {"/api/mother-chat/session", "/api/mother-chat", "/api/mother-chat/logout", "/api/mother-chat/clear"}
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
            if path == "/api/mother-chat/clear":
                payload = read_json_body(self)
                if payload:
                    raise MotherChatError("CHAT_CLEAR_PAYLOAD_INVALID", 400)
                if _HOSHYAR_LOCAL_ASSISTANT is None:
                    raise MotherChatError("HOSHYAR_MEMORY_DISABLED", 409)
                _HOSHYAR_LOCAL_ASSISTANT.clear_memory()
                return self._send(200, b'{"status":"CLEARED","memory_cleared":true,"execution_enabled":false,"orders_placed":false}', "application/json")
            payload = read_json_body(self)
            if set(payload) not in ({"message"}, {"message", "language"}):
                raise MotherChatError("CHAT_MESSAGE_PAYLOAD_INVALID", 400)
            language = payload.get("language", "auto")
            if not isinstance(language, str) or language not in {"auto", "fa", "en", "de", "fr"}:
                raise MotherChatError("CHAT_LANGUAGE_INVALID", 400)
            message = payload.get("message")
            readers = _mother_chat_readers(message if isinstance(message, str) else "")
            if _HOSHYAR_LOCAL_ASSISTANT is not None:
                result = _HOSHYAR_LOCAL_ASSISTANT.respond(message, readers, language=language)
            else:
                result = build_chat_response(message, readers, language=language)
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
