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
from forward.global_market_data_reader_v1 import load_market_input
from forward.native_ohlcv_gateio_v1 import (
    VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES, VOLUME_SEMANTICS_CONTRACT_VERSION,
    TRADE_COUNT_AVAILABLE, TAKER_BUY_FLOW_AVAILABLE)
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.signal_agent_v1 import RiskGeometryV1, SignalAgentV1
from forward.strategy_evidence_provider_v1 import StrategyEvidenceProviderV1
from forward.agent_disagreement_resolver_v1 import AgentAssessmentV1, AgentDisagreementResolverV1
from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.trade_journal_view_v1 import configured_decision_journal, JournalProjectionError
from core.orchestration.mother_v1 import MotherOrchestratorV1, precomputed_specialists_v1
from core.orchestration.witness_v1 import MotherAuditWitnessV1
from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain
from core.market_intelligence.news_monitor import NewsMonitorV1
from forward.decision_engine_v1 import DecisionResult
from forward.news_decision_gate_v1 import apply_news_veto
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream

SUPPORTED_SYMBOLS = {"BTCUSDT"}
SUPPORTED_INTERVALS = {"15m", "1h", "4h"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
        market = load_market_input(root=PROJECT_ROOT)
        if market.get("source") != "gateio_public_spot" or market.get("symbol") != "BTC_USDT":
            raise ValueError("persisted global source identity mismatch")
        rows = market["timeframes"].get(interval, [])[-limit:]
        if len(rows) < 200:
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
_SIGNAL_AGENT = SignalAgentV1(allowed_scopes=(("gateio", "spot", "BTCUSDT", "15m"),))
_STRATEGY_PROVIDER = StrategyEvidenceProviderV1(allowed_scopes=(("gateio", "spot", "BTCUSDT"),))
_ARBITRATION_RESOLVER = AgentDisagreementResolverV1()
_MOTHER_ORCHESTRATOR = MotherOrchestratorV1(precomputed_specialists_v1())
_MOTHER_WITNESS = MotherAuditWitnessV1()
_NEWS_BRAIN = NewsIntelligenceBrain()
_NEWS_REGISTRY = PROJECT_ROOT / "config" / "news_sources_v1.json"
_NEWS_CACHE_LOCK = Lock()
_NEWS_CACHE = {}
_NEWS_CACHE_TTL_SECONDS = 60
_NEWS_REFRESH_LOCK = Lock()
_NEWS_CONTEXT = MarketContext(market="crypto", symbol="BTCUSDT", regime="unknown", timeframe="15m", venue="gateio")
_NEWS_MONITOR_INTERVAL = int(os.environ.get("HES_NEWS_MONITOR_INTERVAL_SECONDS", "60"))
_NEWS_MONITOR_SNAPSHOT = Path(os.environ.get("HES_NEWS_MONITOR_SNAPSHOT", str(PROJECT_ROOT / "data" / "news" / "news_brief_latest.json")))
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
    if age_ms < 0 or age_ms > max(180_000, INTERVAL_MS[interval] * 2):
        raise ValueError("latest_closed_candle_stale")
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

def _cache_monitored_news_brief(brief):
    key = (_NEWS_CONTEXT.market, _NEWS_CONTEXT.symbol, _NEWS_CONTEXT.regime, _NEWS_CONTEXT.timeframe, _NEWS_CONTEXT.venue)
    with _NEWS_CACHE_LOCK:
        _NEWS_CACHE[key] = (time.monotonic(), brief)

_NEWS_MONITOR = NewsMonitorV1(
    brain=_NEWS_BRAIN, registry_path=_NEWS_REGISTRY, context=_NEWS_CONTEXT,
    snapshot_path=_NEWS_MONITOR_SNAPSHOT, interval_seconds=_NEWS_MONITOR_INTERVAL,
    on_brief=_cache_monitored_news_brief,
)
_NEWS_MONITOR_STOP = Event()
_NEWS_MONITOR_THREAD = None

def _get_news_brief(context):
    key = (context.market, context.symbol, context.regime, context.timeframe, context.venue)
    now = time.monotonic()
    with _NEWS_CACHE_LOCK:
        cached = _NEWS_CACHE.get(key)
        if cached and now - cached[0] <= _NEWS_CACHE_TTL_SECONDS:
            return cached[1]
    # Serialize cache misses so concurrent dashboard requests never fan out duplicate source polls.
    with _NEWS_REFRESH_LOCK:
        now = time.monotonic()
        with _NEWS_CACHE_LOCK:
            cached = _NEWS_CACHE.get(key)
            if cached and now - cached[0] <= _NEWS_CACHE_TTL_SECONDS:
                return cached[1]
        brief = _NEWS_BRAIN.run_from_registry(_NEWS_REGISTRY, context)
        with _NEWS_CACHE_LOCK:
            _NEWS_CACHE[key] = (time.monotonic(), brief)
        return brief


def _get_batch(symbol, interval):
    now_ms = int(time.time() * 1000)
    ttl_ms = 75_000 if (symbol, interval) == ("BTCUSDT", "1m") else 15_000
    with _CACHE_LOCK:
        cached = _CACHE.get((symbol, interval))
    if cached and now_ms - cached[2] <= ttl_ms:
        return cached[0], cached[1]
    return _refresh_batch(symbol, interval)

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HES Trade Agent</title><link rel="stylesheet" href="/static/dashboard.css"><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><main><header><div><div class="brand">HES Trade Agent</div><div class="sub">Global feed · persisted closed candles</div></div><span class="pill">HOLD / NO_TRADE_ONLY</span></header>
<section class="panel"><div class="toolbar"><label>Symbol <select id="symbol"><option>BTCUSDT</option></select></label><label>Timeframe <select id="interval"><option>15m</option><option>1h</option><option>4h</option></select></label><button id="refresh">Refresh data</button><span class="muted" id="source">Canonical persisted global feed</span></div>
<div class="metrics"><div class="metric"><small>Last closed close</small><strong id="price">—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" class="stamp">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume">—</strong></div><div class="metric"><small>Closed candles</small><strong id="count">—</strong></div></div>
<div class="panel chart-panel"><div id="chart" role="img" aria-label="Candlestick chart"></div></div><div id="message" role="status">Loading validated closed candles…</div></section>
<section class="panel"><h3 class="panel-title">Signal Agent v1 · BTCUSDT / 15m</h3><div class="metrics"><div class="metric"><small>Decision</small><strong id="signalDecision">NO_TRADE</strong></div><div class="metric"><small>Agent status</small><strong id="signalStatus">Checking gates…</strong></div><div class="metric"><small>Feature quality</small><strong id="signalFeatureQuality">—</strong></div><div class="metric"><small>Strategy quality</small><strong id="signalStrategyQuality">UNKNOWN</strong></div><div class="metric"><small>Strategy quorum</small><strong id="signalStrategyQuorum">0/5</strong></div><div class="metric"><small>Order block score</small><strong id="signalOrderBlock">UNAVAILABLE</strong></div><div class="metric"><small>Risk gate</small><strong id="signalRisk">—</strong></div></div><p class="muted" id="signalReasons">Waiting for validated evidence…</p><div class="gate"><strong>Execution: disabled</strong><p class="muted">This read-only route composes validated market structure, strategy quality, confirmation, risk and arbitration. Missing execution-instrument mapping or any unapproved risk gate keeps the decision at NO_TRADE.</p></div><div class="panel"><h4 class="panel-title">Mother Orchestrator · read-only</h4><div class="metrics"><div class="metric"><small>Orchestration status</small><strong id="motherStatus">BLOCKED</strong></div><div class="metric"><small>Trace / audit</small><strong id="motherTrace">—</strong></div></div><p class="muted" id="motherStages">Waiting for specialist evidence…</p></div><div class="panel"><h4 class="panel-title">News Radar · read-only</h4><div class="metrics"><div class="metric"><small>News status</small><strong id="newsStatus">UNKNOWN</strong></div><div class="metric"><small>News action</small><strong id="newsAction">CONTEXT ONLY</strong></div></div><p class="muted" id="newsSummary">Waiting for qualified source context…</p><p class="muted" id="newsFlags">No news flags loaded.</p><p class="muted" id="newsMonitor">Continuous monitor: waiting for first verified poll…</p></div><div class="metrics"><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<section class="panel"><h3 class="panel-title">Decision and safety gates</h3><div class="gate"><strong>Execution: disabled</strong><p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<section class="panel" id="journalPanel"><div class="toolbar"><div><h3 class="panel-title">Trade Journal · Decision & Learning Evidence</h3><div class="muted">Immutable forward decisions only. Executed trades and realized outcomes are not inferred from a signal.</div></div><button id="journalRefresh" type="button">Refresh journal</button></div><p class="muted" id="journalStatus" role="status">Loading journal…</p><div class="journal-scroll"><table class="journal-table"><thead><tr><th>Time (UTC)</th><th>Market</th><th>Decision</th><th>Gate / reason</th><th>Outcome</th><th>Evidence</th></tr></thead><tbody id="journalRows"><tr><td colspan="6" class="muted">No journal entries loaded.</td></tr></tbody></table></div></section>
<div class="footer">Charts powered by <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. Copyright (c) 2025 TradingView, Inc. The chart reads the same validated persisted Gate.io candles through the canonical global-market reader used by the analysis input path; the dashboard does not make a second REST candle request. This is a single public venue source, not a cross-venue consolidated index. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Base and quote volume fields follow Gate.io's documented candlestick schema and are shown unchanged; trade count and taker-buy flow are unavailable. If the source is unavailable or stale, the chart fails closed.</div></main>
<script src="/static/dashboard.js" defer></script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version = "HESReadOnlyDashboard/1.0"
    def _send(self,status,body,content_type):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
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
        if p.path in ("/static/dashboard.css", "/static/dashboard.js"):
            asset_path = Path(__file__).resolve().parent / "static" / Path(p.path).name
            content_type = "text/css; charset=utf-8" if p.path.endswith(".css") else "text/javascript; charset=utf-8"
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
                if latest_age_seconds < 0 or latest_age_seconds > max(180, INTERVAL_MS["15m"] * 2 / 1000):
                    raise ValueError("latest_closed_candle_stale")
                if batch.gaps:
                    raise ValueError("persisted_candle_gaps_present")
                payload = {
                    "status": "ok", "mode": "NO_TRADE_ONLY", "execution_enabled": False, "orders_placed": False,
                    "source": "gateio_public_spot", "source_reader": "global_market_data_reader_v1",
                    "source_symbol": "BTC_USDT", "symbol_mapping_verified": True,
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
        if p.path == "/api/news":
            try:
                snapshot = _NEWS_MONITOR.read_snapshot(max_age_seconds=max(180, _NEWS_MONITOR_INTERVAL * 3))
                monitor = snapshot["monitor"]
                if monitor["status"] == "BLOCKED" or snapshot.get("brief") is None:
                    raise ValueError("news_monitor_blocked")
                return self._send(200, json.dumps(snapshot, separators=(",", ":")).encode(), "application/json")
            except Exception as exc:
                return self._send(503, json.dumps({
                    "status": "BLOCKED", "error": type(exc).__name__,
                    "fail_closed": True, "execution_enabled": False, "orders_placed": False,
                }, separators=(",", ":")).encode(), "application/json")
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
        if p.path == "/api/signal":
            q = parse_qs(p.query)
            symbol = q.get("symbol", ["BTCUSDT"])[0]
            interval = q.get("interval", ["15m"])[0]
            if symbol != "BTCUSDT" or interval != "15m":
                return self._send(400, b'{"error":"unsupported_signal_scope","decision":"NO_TRADE","execution_enabled":false,"orders_placed":false}', "application/json")
            try:
                # Reuse the canonical persisted reader for both the chart-aligned 15m
                # batch and its 4h context. No independent candle fetch or indicator engine.
                batch, feature_result = _get_batch(symbol, interval)
                htf_batch, _ = _get_batch(symbol, "4h")
                strategy = _STRATEGY_PROVIDER.evaluate(
                    candles_15m=batch,
                    candles_4h=htf_batch,
                    now_ms=int(time.time() * 1000),
                )
                geometry = (
                    RiskGeometryV1(
                        entry=str(strategy.risk_geometry[0]),
                        stop_loss=str(strategy.risk_geometry[1]),
                        take_profit=str(strategy.risk_geometry[2]),
                    )
                    if strategy.risk_geometry is not None else None
                )
                result = _SIGNAL_AGENT.evaluate(
                    observed_at=strategy.observed_at,
                    venue=batch.venue,
                    product=batch.product,
                    symbol=batch.symbol,
                    timeframe=batch.interval,
                    regime=strategy.regime,
                    structure_labels=strategy.structure_labels,
                    structure_events=strategy.structure_events,
                    structure_direction=strategy.direction,
                    strategy_checks=strategy.strategy_checks,
                    confirmation_checks=strategy.confirmation_checks,
                    risk_checks=strategy.risk_checks,
                    risk_geometry=geometry,
                )
                quality = result.strategy_quality
                order_block = strategy.order_block
                data_ok = bool(feature_result.decision_ready and getattr(feature_result.quality, "passed", False)
                               and not batch.gaps and not htf_batch.gaps)
                structure_ok = strategy.direction in ("BULLISH", "BEARISH") and (
                    (strategy.regime == "UPTREND" and strategy.direction == "BULLISH")
                    or (strategy.regime == "DOWNTREND" and strategy.direction == "BEARISH")
                )
                direction = "LONG" if strategy.direction == "BULLISH" else "SHORT" if strategy.direction == "BEARISH" else "UNKNOWN"
                observed_at = strategy.observed_at

                def evidence_hash(value):
                    return hashlib.sha256(json.dumps(
                        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
                    ).encode("utf-8")).hexdigest()

                snapshot_sha256 = evidence_hash({
                    "source": "gateio_public_spot",
                    "15m_batch_sha256": batch.response_sha256,
                    "4h_batch_sha256": htf_batch.response_sha256,
                    "observed_at": observed_at.isoformat(),
                })
                confirmation_state = getattr(result.confirmation, "state", "UNKNOWN")
                confirmation_gate = (
                    "PASS" if confirmation_state in ("CONFIRMED_LONG", "CONFIRMED_SHORT")
                    else "FAIL" if "REJECT" in str(confirmation_state) or "BLOCK" in str(confirmation_state)
                    else "UNKNOWN"
                )
                risk_gate = (
                    "PASS" if result.risk.state == "RISK_APPROVED"
                    else "FAIL" if result.risk.state == "RISK_REJECTED"
                    else "UNKNOWN"
                )
                strategy_state = quality.state if quality else "UNKNOWN"
                data_state = "PASS" if data_ok else "FAIL" if getattr(feature_result, "quality", None) is not None else "UNKNOWN"
                structure_state = "PASS" if structure_ok else "UNKNOWN"
                structure_digest = evidence_hash({
                    "direction": strategy.direction, "regime": strategy.regime,
                    "labels": strategy.structure_labels, "events": strategy.structure_events,
                    "source_sha256": batch.response_sha256,
                })
                strategy_digest = (
                    quality.evidence_sha256 if quality and quality.evidence_sha256
                    else evidence_hash([{
                        "name": c.name, "state": c.state, "evidence_sha256": c.evidence_sha256
                    } for c in strategy.strategy_checks])
                )
                confirmation_digest = evidence_hash([{
                    "name": c.name, "state": c.state, "evidence_ref": c.evidence_ref
                } for c in result.confirmation.checks])
                risk_digest = evidence_hash([{
                    "name": c.name, "state": c.state, "evidence_ref": c.evidence_ref
                } for c in result.risk.checks])
                assessments = (
                    AgentAssessmentV1(
                        "data_quality", "native-feature-pipeline-v1", data_state, "NEUTRAL",
                        batch.venue, batch.product, batch.symbol, batch.interval, observed_at,
                        snapshot_sha256, batch.response_sha256,
                        () if data_ok else ("NATIVE_FEATURES_NOT_READY",),
                    ),
                    AgentAssessmentV1(
                        "market_structure", "strategy-market-structure-v1", structure_state, direction,
                        batch.venue, batch.product, batch.symbol, batch.interval, observed_at,
                        snapshot_sha256, structure_digest,
                        () if structure_ok else ("STRUCTURE_DIRECTION_UNKNOWN_OR_MISMATCHED",),
                    ),
                    AgentAssessmentV1(
                        "strategy", _STRATEGY_PROVIDER.VERSION, strategy_state, direction,
                        batch.venue, batch.product, batch.symbol, batch.interval, observed_at,
                        snapshot_sha256, strategy_digest,
                        tuple(quality.reason_codes) if quality else ("STRATEGY_QUALITY_UNKNOWN",),
                    ),
                    AgentAssessmentV1(
                        "confirmation", "confirmation-engine-v1", confirmation_gate, direction,
                        batch.venue, batch.product, batch.symbol, batch.interval, observed_at,
                        snapshot_sha256, confirmation_digest,
                        tuple(getattr(result.confirmation, "reason_codes", ())),
                    ),
                    AgentAssessmentV1(
                        "risk", "risk-gate-v1", risk_gate, direction,
                        batch.venue, batch.product, batch.symbol, batch.interval, observed_at,
                        snapshot_sha256, risk_digest, tuple(result.risk.reason_codes),
                    ),
                )
                arbitration = _ARBITRATION_RESOLVER.resolve(
                    assessments=assessments, observed_at=observed_at
                )
                # Reuse the existing free-first news brain. News is metadata/veto
                # only; it cannot create a direction or bypass confirmation/risk.
                news_brief = _get_news_brief(
                    MarketContext(
                        market="crypto", symbol=batch.symbol, regime=strategy.regime or "unknown",
                        timeframe=batch.interval, observed_at=observed_at.isoformat(), venue=batch.venue,
                    ),
                )
                news_input = DecisionResult(
                    observed_at=observed_at, decision=arbitration.decision,
                    reason_codes=tuple(arbitration.reason_codes),
                    evidence_refs=(batch.response_sha256, htf_batch.response_sha256),
                    quality_score=result.decision.quality_score,
                )
                news_decision = apply_news_veto(news_input, news_brief)
                effective_decision = news_decision.decision
                news_veto_flags = sorted(set(news_decision.reason_codes) - set(arbitration.reason_codes))
                news_context_payload = news_brief.to_mother_payload()
                news_context_payload["decision_veto_flags"] = news_veto_flags

                # Mother is a bounded control plane over these existing outputs.
                # It validates order/provenance/vetoes; it does not recalculate indicators.
                def report(state, version, reasons, refs, payload=None):
                    return {
                        "state": state,
                        "agent_version": version,
                        "reason_codes": list(dict.fromkeys(str(x) for x in reasons if isinstance(x, str) and x)),
                        "evidence_refs": list(dict.fromkeys(str(x) for x in refs if isinstance(x, str) and x)),
                        "payload": payload if payload is not None else {},
                    }
                common_refs = [snapshot_sha256, batch.response_sha256, htf_batch.response_sha256]
                confirmed = confirmation_gate == "PASS"
                execution_instrument_mapping_verified = False
                risk_approved = result.risk.state == "RISK_APPROVED" and execution_instrument_mapping_verified
                signal_ready = bool(quality and quality.state == "PASS" and result.candidate.state in ("CANDIDATE_LONG", "CANDIDATE_SHORT"))
                specialist_reports = {
                    "data_quality": report(
                        data_state, "native-feature-pipeline-v1",
                        () if data_ok else ("NATIVE_FEATURES_NOT_READY",), common_refs,
                        {"decision_ready": bool(feature_result.decision_ready)},
                    ),
                    "market_structure": report(
                        "PASS" if structure_ok else "UNKNOWN", "strategy-market-structure-v1",
                        () if structure_ok else ("STRUCTURE_DIRECTION_UNKNOWN_OR_MISMATCHED",), common_refs,
                        {"direction": strategy.direction, "regime": strategy.regime},
                    ),
                    "signal": report(
                        "PASS" if signal_ready else "UNKNOWN", _SIGNAL_AGENT.VERSION,
                        () if signal_ready else ("SIGNAL_CANDIDATE_NOT_APPROVED",), common_refs,
                        {"decision": result.decision.decision},
                    ),
                    "confirmation": report(
                        "CONFIRMED" if confirmed else "UNKNOWN", "confirmation-engine-v1",
                        () if confirmed else tuple(getattr(result.confirmation, "reason_codes", ()),), common_refs,
                        {"state": confirmation_state},
                    ),
                    "risk": report(
                        "APPROVED" if risk_approved else "UNKNOWN", "risk-gate-v1",
                        () if risk_approved else tuple(result.risk.reason_codes) or ("INDEPENDENT_RISK_APPROVAL_MISSING",),
                        common_refs, {"state": result.risk.state, "execution_enabled": False},
                    ),
                    "decision": report(
                        "DECIDED", "decision-engine-v1", tuple(result.decision.reason_codes), common_refs,
                        {"decision": effective_decision, "news_context": news_context_payload},
                    ),
                    "evaluation": report(
                        "OBSERVED", "forward-learning-observation-v1", ("OUTCOME_NOT_INFERRED",), common_refs,
                        {"journal_status": "CANONICAL_TRADE_JOURNAL"},
                    ),
                }
                report_digest = evidence_hash(specialist_reports)
                mother_context = {
                    "scope": {
                        "venue": batch.venue, "product": batch.product,
                        "symbol": batch.symbol, "timeframe": batch.interval,
                    },
                    "observed_at": observed_at.isoformat(),
                    "snapshot_sha256": snapshot_sha256,
                    "evidence_sha256": report_digest,
                    "specialist_reports": specialist_reports,
                }
                mother_result = _MOTHER_ORCHESTRATOR.run(mother_context)
                mother_envelope = mother_result.as_dict()
                mother_witness = _MOTHER_WITNESS.verify(mother_envelope).as_dict()

                blocked = list(strategy.blocked_reasons) + list(result.blocked_reasons)
                if arbitration.decision == "NO_TRADE":
                    blocked.extend(arbitration.reason_codes)
                if effective_decision == "NO_TRADE" and arbitration.decision != "NO_TRADE":
                    blocked.extend(news_veto_flags)
                # Market-data symbol mapping is verified; executable instrument mapping is not.
                blocked.append("EXECUTION_INSTRUMENT_MAPPING_UNVERIFIED")
                if not feature_result.decision_ready:
                    blocked.append("NATIVE_FEATURES_NOT_READY")
                if batch.gaps or htf_batch.gaps:
                    blocked.append("NATIVE_CANDLE_GAPS_PRESENT")
                if not mother_witness.get("verified", False):
                    blocked.append("MOTHER_AUDIT_WITNESS_FAILED")
                if mother_result.decision == "NO_TRADE":
                    blocked.extend(mother_result.reason_codes)
                final_decision = effective_decision if not blocked and mother_result.decision != "NO_TRADE" else "NO_TRADE"
                payload = {
                    "status": "BLOCKED" if blocked or final_decision == "NO_TRADE" else "READY",
                    "agent_version": _SIGNAL_AGENT.VERSION,
                    "strategy_provider_version": _STRATEGY_PROVIDER.VERSION,
                    "decision": final_decision,
                    "decision_reasons": list(result.decision.reason_codes),
                    "blocked_reasons": list(dict.fromkeys(blocked)),
                    "observed_at": observed_at.isoformat(),
                    "symbol": batch.symbol,
                    "timeframe": batch.interval,
                    "source": "gateio_public_spot",
                    "source_reader": batch.endpoint_kind,
                    "source_symbol": "BTC_USDT",
                    "symbol_mapping_verified": True,
                    "execution_instrument_mapping_verified": False,
                    "product": batch.product,
                    "input_batch_sha256": batch.response_sha256,
                    "response_sha256": batch.response_sha256,
                    "strategy_15m_batch_sha256": batch.response_sha256,
                    "strategy_4h_batch_sha256": htf_batch.response_sha256,
                    "feature_ready": feature_result.decision_ready,
                    "feature_reason": feature_result.reason,
                    "feature_quality_passed": feature_result.quality.passed,
                    "strategy_quality_state": strategy_state,
                    "strategy_quality_passed_count": quality.passed_count if quality else 0,
                    "strategy_quality_required_count": quality.required_count if quality else 5,
                    "strategy_evidence_sha256": quality.evidence_sha256 if quality else None,
                    "structure_direction": strategy.direction,
                    "regime": strategy.regime,
                    "mfi14": strategy.mfi14,
                    "adx14": strategy.adx14,
                    "plus_di14": strategy.plus_di14,
                    "minus_di14": strategy.minus_di14,
                    "ema50_15m": strategy.ema50_15m,
                    "ema50_4h": strategy.ema50_4h,
                    "ema200_4h": strategy.ema200_4h,
                    "mfi_divergence": strategy.mfi_divergence,
                    "order_block_score": getattr(order_block, "score", None),
                    "order_block_max_score": getattr(order_block, "max_score", 7),
                    "order_block_fresh": getattr(order_block, "fresh", None),
                    "order_block_mitigated": getattr(order_block, "mitigated", None),
                    "risk_state": result.risk.state,
                    "risk_reasons": list(result.risk.reason_codes),
                    "arbitration_decision": arbitration.decision,
                    "news_context": news_context_payload,
                    "news_veto_applied": bool(news_veto_flags) and effective_decision != arbitration.decision,
                    "news_decision": effective_decision,
                    "news_veto_flags": news_veto_flags,
                    "arbitration_conflict_class": arbitration.conflict_class,
                    "arbitration_reason_codes": list(arbitration.reason_codes),
                    "arbitration_audit_sha256": arbitration.audit_sha256,
                    "arbitration_assessments": [dict(item) for item in arbitration.assessments],
                    "mother_orchestration": mother_envelope,
                    "mother_witness": mother_witness,
                    "execution_enabled": False, "orders_placed": False,
                    "learning_journal_status": "NOT_CONFIGURED",
                    "learning_event_id": None,
                }

                # Every Signal Agent decision is appended to the same canonical
                # trade_journal_v2 used by the existing paper evaluator and Learning Loop.
                # No parallel decision journal or outcome ledger is created.
                journal_path = os.environ.get(
                    "HES_TRADE_JOURNAL_PATH",
                    str(PROJECT_ROOT / "data" / "forward" / "trade_journal_v2.jsonl"),
                )
                if not batch.response_sha256 or not htf_batch.response_sha256:
                    payload["learning_journal_status"] = "BLOCKED_MISSING_SOURCE_IDENTITY"
                else:
                    if not data_ok:
                        rejected_at = "DATA_QUALITY"
                    elif not structure_ok:
                        rejected_at = "MARKET_STRUCTURE"
                    elif strategy_state != "PASS":
                        rejected_at = "STRATEGY_QUALITY"
                    elif confirmation_gate != "PASS":
                        rejected_at = "CONFIRMATION"
                    elif risk_gate != "PASS":
                        rejected_at = "RISK"
                    elif news_veto_flags:
                        rejected_at = "NEWS"
                    elif arbitration.decision == "NO_TRADE":
                        rejected_at = "ARBITRATION"
                    else:
                        rejected_at = "EXECUTION_MAPPING"
                    try:
                        journal_result = record_signal_decision(
                            journal_path,
                            decision=final_decision,
                            observed_at=observed_at.isoformat(),
                            symbol=batch.symbol,
                            timeframe=batch.interval,
                            source="gateio_native_ohlcv_v1",
                            product=batch.product,
                            response_sha256=batch.response_sha256,
                            htf_response_sha256=htf_batch.response_sha256,
                            strategy_evidence_sha256=quality.evidence_sha256 if quality else None,
                            policy_version=f"{_SIGNAL_AGENT.VERSION}+{_STRATEGY_PROVIDER.VERSION}",
                            status=payload["status"],
                            market_regime=strategy.regime or "UNKNOWN",
                            rejected_at=rejected_at,
                            reason_codes=list(dict.fromkeys(blocked + list(arbitration.reason_codes))),
                            direction=direction if direction in ("LONG", "SHORT") else "NONE",
                            signal_state=result.candidate.state,
                            confirmation_state=confirmation_state,
                            risk_state=result.risk.state,
                            entry=geometry.entry if geometry else None,
                            stop_loss=geometry.stop_loss if geometry else None,
                            take_profit=geometry.take_profit if geometry else None,
                            proposal_decision=result.decision.decision,
                            structure_events=list(strategy.structure_events),
                            structure_labels=list(strategy.structure_labels),
                            confirmation_reasons=list(getattr(result.confirmation, "reason_codes", ())),
                            risk_reasons=list(result.risk.reason_codes),
                        )
                        payload["learning_journal_status"] = journal_result.status
                        payload["learning_event_id"] = journal_result.event_id
                        payload["learning_event_sha256"] = journal_result.digest
                    except Exception as exc:
                        payload["learning_journal_status"] = "BLOCKED_JOURNAL_ERROR"
                        payload["learning_journal_error"] = type(exc).__name__
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except Exception as exc:
                return self._send(503, json.dumps({
                    "error": "signal_input_unavailable",
                    "reason": type(exc).__name__,
                    "status": "BLOCKED",
                    "decision": "NO_TRADE",
                    "fail_closed": True,
                    "execution_enabled": False, "orders_placed": False,
                }).encode(), "application/json")
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
                "symbol":batch.symbol,"source_symbol":"BTC_USDT","symbol_mapping_verified":True,
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
            return self._send(503,json.dumps({"error":"market_data_unavailable",
                "reason":type(exc).__name__,"fail_closed":True,"execution_enabled":False,"orders_placed":False}).encode(),"application/json")
    def do_POST(self): return self._send(405,b'{"error":"method_not_allowed","execution_enabled":false,"orders_placed":false}',"application/json")
    def log_message(self,fmt,*args):
        if os.environ.get("HES_DASHBOARD_ACCESS_LOG")=="1": super().log_message(fmt,*args)

def main():
    # The legacy Binance stream is deliberately not started by the Gate.io chart path.
    # Gate.io candles are REST-refreshed; a matching Gate.io stream needs its own
    # source-identity/reconciliation tests before it can be enabled.
    _STREAM_STATE.update(status="disabled", reason="gateio_stream_not_enabled")
    host=os.environ.get("HES_DASHBOARD_HOST","127.0.0.1"); port=int(os.environ.get("HES_DASHBOARD_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    global _NEWS_MONITOR_THREAD
    _NEWS_MONITOR_THREAD = Thread(target=_NEWS_MONITOR.run_forever, args=(_NEWS_MONITOR_STOP,), name="hes-news-monitor", daemon=True)
    _NEWS_MONITOR_THREAD.start()
    print(f"HES read-only dashboard listening on http://{host}:{port}",flush=True)
    try:
        server.serve_forever()
    finally:
        _NEWS_MONITOR_STOP.set()
        if _NEWS_MONITOR_THREAD.is_alive():
            _NEWS_MONITOR_THREAD.join(timeout=5)
        server.server_close()

if __name__=="__main__": main()
