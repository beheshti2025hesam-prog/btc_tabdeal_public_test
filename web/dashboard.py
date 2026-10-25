"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
import json, os, time
from urllib.parse import parse_qs, urlparse
from forward.native_ohlcv_v1 import BinanceSpotKlineSource, INTERVAL_MS, validate_native_batch
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream
from forward.signal_agent_v1 import RiskGeometryV1, SignalAgentV1
from forward.agent_disagreement_resolver_v1 import AgentAssessmentV1, AgentDisagreementResolverV1
from forward.strategy_evidence_provider_v1 import StrategyEvidenceProviderV1
from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.trade_journal_view_v1 import configured_decision_journal, JournalProjectionError
from forward.execution_journal_view_v1 import configured_execution_journal, ExecutionJournalProjectionError
from forward.trade_journal_outcome_view_v1 import configured_outcome_projection, OutcomeProjectionError

SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
CHART_ASSET_PATH = "/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js"
CHART_ASSET_FILE = Path(__file__).resolve().parent / "static" / "third_party" / "lightweight-charts" / "5.0.8" / "lightweight-charts.standalone.production.js"
_SOURCE = BinanceSpotKlineSource()
# Binance Spot documents base-asset volume and quote-asset volume separately:
# https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#klinecandlestick-streams-for-utc
# This approval is source-specific; never reuse it for Wallex or another venue.
_FEATURES = NativeOHLCVFeaturePipelineV1(volume_semantics_approved=True)
_SIGNAL_AGENT = SignalAgentV1()
_DISAGREEMENT_RESOLVER = AgentDisagreementResolverV1()
_STRATEGY_PROVIDER = StrategyEvidenceProviderV1()
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

def _get_batch(symbol, interval):
    now_ms = int(time.time() * 1000)
    ttl_ms = 75_000 if (symbol, interval) == ("BTCUSDT", "1m") else 300_000 if interval == "4h" else 15_000
    with _CACHE_LOCK:
        cached = _CACHE.get((symbol, interval))
    if cached and now_ms - cached[2] <= ttl_ms:
        return cached[0], cached[1]
    return _refresh_batch(symbol, interval)

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HES Trade Agent</title><style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#121c2c;--line:#27364b;--muted:#91a2ba;--text:#e8eff8;--green:#36c98f;--red:#f16b75;--amber:#f2bf58}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:22px}
header,.toolbar,.metrics{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.brand{font-weight:750;font-size:22px}.sub,.muted{color:var(--muted);font-size:13px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:16px}.pill{border:1px solid #765e2e;color:var(--amber);padding:7px 10px;border-radius:999px;font-size:12px}
.metrics{justify-content:flex-start;margin-top:14px}.metric{min-width:150px;flex:1}.metric small{display:block;color:var(--muted)}.metric strong{font-size:20px;display:block;margin-top:5px}
.toolbar{justify-content:flex-start}button,select{background:#1b2a40;color:var(--text);border:1px solid #34465e;padding:9px 12px;border-radius:8px;font:inherit}button{cursor:pointer}#chart{display:block;width:100%;height:390px}
#message{color:var(--muted);font-size:13px;margin-top:10px}.gate{border-left:3px solid var(--amber);padding-left:12px}.footer{padding:18px 2px;color:var(--muted);font-size:12px;line-height:1.6}
@media(max-width:600px){main{padding:12px}#chart{height:300px}.metric{min-width:42%}}
</style><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><main><header><div><div class="brand">HES Trade Agent</div><div class="sub">Binance Spot · native closed candles</div></div><span class="pill">HOLD / NO_TRADE_ONLY</span></header>
<section class="panel"><div class="toolbar"><label>Symbol <select id="symbol"><option>BTCUSDT</option><option>ETHUSDT</option><option>SOLUSDT</option></select></label><label>Timeframe <select id="interval"><option>1m</option><option>5m</option><option>15m</option><option>1h</option><option>1d</option></select></label><button id="refresh">Refresh data</button><span class="muted" id="source">Binance Spot public klines</span></div>
<div class="metrics"><div class="metric"><small>Last closed close</small><strong id="price">—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" style="font-size:14px">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume">—</strong></div><div class="metric"><small>Closed candles</small><strong id="count">—</strong></div></div>
<div class="panel" style="padding:8px;margin-top:14px"><div id="chart" role="img" aria-label="Candlestick chart"></div></div><div id="message" role="status">Loading validated closed candles…</div></section>
<section class="panel"><h3 style="margin-top:0">Signal Agent v1 · BTCUSDT / 15m</h3><div class="metrics"><div class="metric"><small>Decision</small><strong id="signalDecision">NO_TRADE</strong></div><div class="metric"><small>Agent status</small><strong id="signalStatus">Checking gates…</strong></div><div class="metric"><small>Feature quality</small><strong id="signalFeatureQuality">—</strong></div><div class="metric"><small>Strategy quality</small><strong id="signalStrategyQuality">UNKNOWN</strong></div><div class="metric"><small>Strategy quorum</small><strong id="signalStrategyQuorum">0/5</strong></div><div class="metric"><small>Order block score</small><strong id="signalOrderBlock">UNAVAILABLE</strong></div><div class="metric"><small>Risk gate</small><strong id="signalRisk">—</strong></div></div><p class="muted" id="signalReasons">Waiting for validated evidence…</p><div class="gate"><strong>Execution: disabled</strong><p class="muted">This is the read-only Signal Agent entry route. Missing symbol-mapping evidence, directional structure, strategy-level quality approval, risk geometry, or any risk approval keeps the decision at NO_TRADE. Feature-engine quality is descriptive and is not substituted for strategy-level signal quality.</p></div><div class="metrics"><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<section class="panel" id="journalPanel"><div class="toolbar"><div><h3 style="margin:0">Trade Journal · Decision & Learning Evidence</h3><div class="muted">Immutable forward decisions only. This is not a statement of executed trades; realized outcomes remain UNKNOWN until separately reconciled.</div></div><button id="journalRefresh" type="button">Refresh journal</button></div><p class="muted" id="journalStatus" role="status">Loading journal…</p><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr><th align="left">Time (UTC)</th><th align="left">Market</th><th align="left">Decision</th><th align="left">Gate / reason</th><th align="left">Outcome</th><th align="left">Evidence</th></tr></thead><tbody id="journalRows"><tr><td colspan="6" class="muted">No journal entries loaded.</td></tr></tbody></table></div></section>
<section class="panel" id="executionJournalPanel"><div class="toolbar"><div><h3 style="margin:0">Execution Lifecycle · Read-only</h3><div class="muted">Reads the existing durable execution journal only. No order actions; fees, funding and realized P&amp;L remain UNKNOWN until reconciled.</div></div><button id="executionJournalRefresh" type="button">Refresh execution</button></div><p class="muted" id="executionJournalStatus" role="status">Execution journal is not configured unless an explicit durable path is provided.</p><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr><th align="left">Decision ID</th><th align="left">Order ID</th><th align="left">Lifecycle</th><th align="left">Filled quantity</th><th align="left">Avg. fill</th><th align="left">Fees / funding / P&amp;L</th><th align="left">Evidence</th></tr></thead><tbody id="executionJournalRows"><tr><td colspan="7" class="muted">No execution lifecycle entries loaded.</td></tr></tbody></table></div></section>
<div class="footer">Charts powered by <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. Copyright (c) 2025 TradingView, Inc. Binance Spot is venue-specific, not a consolidated global feed. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Volume is shown as reported and is not normalized; its semantics are unverified. If the source is unavailable or stale, the chart fails closed.</div></main>
<script>
const $=id=>document.getElementById(id);let bars=[];let chart=null,candleSeries=null;
if(window.LightweightCharts){chart=LightweightCharts.createChart($('chart'),{autoSize:true,layout:{background:{type:'solid',color:'#121c2c'},textColor:'#91a2ba'},grid:{vertLines:{color:'#27364b'},horzLines:{color:'#27364b'}},rightPriceScale:{borderColor:'#27364b'},timeScale:{borderColor:'#27364b',timeVisible:true,secondsVisible:false},crosshair:{vertLine:{color:'#526783'},horzLine:{color:'#526783'}}});candleSeries=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#36c98f',downColor:'#f16b75',borderVisible:false,wickUpColor:'#36c98f',wickDownColor:'#f16b75'});}
function draw(){if(!candleSeries){$('message').textContent='FAIL CLOSED · chart library did not load; check network/CDN policy';return}candleSeries.setData(bars.map(b=>({time:Math.floor(b.open_time/1000),open:Number(b.open),high:Number(b.high),low:Number(b.low),close:Number(b.close)})));if(bars.length)chart.timeScale().fitContent()}
async function refresh(){const btn=$('refresh');btn.disabled=true;$('message').textContent='Fetching and validating closed reference candles…';try{const q=new URLSearchParams({symbol:$('symbol').value,interval:$('interval').value}),r=await fetch('/api/candles?'+q,{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Market data unavailable');bars=j.candles;if(!bars.length)throw Error('No closed candles returned');const b=bars[bars.length-1];$('price').textContent=Number(b.close).toLocaleString(undefined,{maximumFractionDigits:8});$('stamp').textContent=new Date(b.close_time).toISOString().replace('T',' ').replace('.000Z',' UTC');$('volume').textContent=b.volume;$('count').textContent=String(bars.length);$('source').textContent='Source: '+j.source+' · '+j.product+' · '+j.symbol;$('message').textContent='VALIDATED · '+(j.feature_ready?'FEATURES READY':'FEATURES GATED: '+j.feature_reason)+' · stream '+j.stream_status+(j.stream_reason?' ('+j.stream_reason+')':'')+' · latest age '+j.latest_age_seconds.toFixed(1)+'s · volume unchanged';draw()}catch(e){bars=[];draw();['price','stamp','volume','count'].forEach(k=>$(k).textContent='—');$('message').textContent='FAIL CLOSED · '+e.message}finally{btn.disabled=false}}
async function refreshJournal(){const status=$('journalStatus'),rows=$('journalRows');status.textContent='Verifying immutable decision journal…';rows.replaceChildren();try{const r=await fetch('/api/journal-outcomes?limit=50',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Journal unavailable');if(j.status==='NOT_CONFIGURED'){status.textContent='NOT CONFIGURED · Set HES_FORWARD_LEARNING_DECISION_JOURNAL to an explicit durable path. No entries are invented.';return}if(j.status==='EMPTY'){status.textContent='VERIFIED · Journal is empty.';return}status.textContent=(j.status==='OUTCOMES_NOT_CONFIGURED'?'DECISIONS VERIFIED · outcomes not configured · ':'VERIFIED · ')+j.count+' decision events'+(j.truncated?' (showing newest 50)':'')+' · execution OFF · outcomes not inferred';for(const e of j.events){const tr=document.createElement('tr');for(const value of [e.observed_at.replace('T',' ').replace('+00:00',' UTC'),e.symbol+' / '+e.timeframe,e.decision,e.rejected_at+(e.reason_codes.length?': '+e.reason_codes.join(', '):''),e.outcome+(e.realized_rr!=='UNKNOWN'?' · R='+e.realized_rr:''),e.outcome_artifact_sha256?e.outcome_artifact_sha256.slice(0,12)+'…':(e.decision_event_sha256||e.event_sha256||'NOT_LINKED').slice(0,12)+'…']){const td=document.createElement('td');td.style.padding='8px 6px';td.style.borderTop='1px solid var(--line)';td.style.verticalAlign='top';td.textContent=value;tr.appendChild(td)}rows.appendChild(tr)}}catch(e){status.textContent='FAIL CLOSED · '+e.message+' · no journal rows shown';rows.replaceChildren()}}
async function refreshExecutionJournal(){const status=$('executionJournalStatus'),rows=$('executionJournalRows');status.textContent='Reading execution journal in read-only mode…';rows.replaceChildren();try{const r=await fetch('/api/execution-journal?limit=50',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Execution journal unavailable');if(j.status==='NOT_CONFIGURED'){status.textContent='NOT CONFIGURED · HES_EXECUTION_JOURNAL_DB is unset. No execution is inferred from decisions.';return}if(j.status==='EMPTY'){status.textContent='VERIFIED · no execution lifecycle records.';return}status.textContent='VERIFIED · '+j.count+' lifecycle records'+(j.truncated?' (showing newest 50)':'')+' · read-only · execution disabled';for(const e of j.orders){const tr=document.createElement('tr');for(const value of [e.decision_id,e.venue_order_id||'UNKNOWN',e.state,e.executed_quantity||'UNKNOWN',e.average_fill_price||'UNKNOWN',e.fees+' / '+e.funding+' / '+e.realized_pnl,e.raw_response_sha256?e.raw_response_sha256.slice(0,12)+'…':'NOT_LINKED']){const td=document.createElement('td');td.style.padding='8px 6px';td.style.borderTop='1px solid var(--line)';td.style.verticalAlign='top';td.textContent=value;tr.appendChild(td)}rows.appendChild(tr)}}catch(e){status.textContent='FAIL CLOSED · '+e.message+' · no execution rows shown';rows.replaceChildren()}}
async function refreshSignal(){try{const r=await fetch('/api/signal?symbol=BTCUSDT&interval=15m',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Signal evaluation unavailable');$('signalDecision').textContent=j.decision;$('signalStatus').textContent=j.status;$('signalFeatureQuality').textContent=j.feature_quality_passed===true?'PASS (descriptive)':j.feature_quality_passed===false?'FAIL':'UNKNOWN';$('signalStrategyQuality').textContent=j.strategy_quality_state||'UNKNOWN';$('signalStrategyQuorum').textContent=String(j.strategy_quality_passed_count??0)+'/'+String(j.strategy_quality_required_count??5);$('signalOrderBlock').textContent=j.order_block_score===null||j.order_block_score===undefined?'UNAVAILABLE':String(j.order_block_score)+'/'+String(j.order_block_max_score??7)+(j.order_block_fresh?' · FRESH':j.order_block_mitigated?' · MITIGATED':'');$('signalRisk').textContent=j.risk_state||'UNKNOWN';$('signalReasons').textContent=(j.blocked_reasons||[]).join(' · ')||'No block reasons supplied';}catch(e){$('signalDecision').textContent='NO_TRADE';$('signalStatus').textContent='BLOCKED';$('signalFeatureQuality').textContent='UNKNOWN';$('signalStrategyQuality').textContent='UNKNOWN';$('signalStrategyQuorum').textContent='0/5';$('signalOrderBlock').textContent='UNKNOWN';$('signalRisk').textContent='UNKNOWN';$('signalReasons').textContent='FAIL CLOSED · '+e.message}}
$('refresh').addEventListener('click',refresh);$('symbol').addEventListener('change',refresh);$('interval').addEventListener('change',refresh);$('journalRefresh').addEventListener('click',refreshJournal);$('executionJournalRefresh').addEventListener('click',refreshExecutionJournal);refresh();refreshSignal();refreshJournal();refreshExecutionJournal();setInterval(refresh,15000);setInterval(refreshSignal,15000);setInterval(refreshJournal,30000);setInterval(refreshExecutionJournal,30000);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version = "HESReadOnlyDashboard/1.0"
    def _send(self,status,body,content_type):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
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
        if p.path=="/healthz": return self._send(200,b'{"status":"ok","mode":"NO_TRADE_ONLY","execution_enabled":false,"source":"binance_native_ohlcv_v1"}',"application/json")
        if p.path == "/api/journal":
            q = parse_qs(p.query)
            try:
                limit = int(q.get("limit", ["50"])[0])
                payload = configured_decision_journal(limit=limit)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (JournalProjectionError, ValueError) as exc:
                payload = {"schema": "hes.trade_journal_view.v1", "status": "BLOCKED",
                           "error": str(exc), "events": [], "count": 0,
                           "execution_enabled": False, "outcomes_inferred": False}
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/journal-outcomes":
            q = parse_qs(p.query)
            try:
                limit = int(q.get("limit", ["50"])[0])
                payload = configured_outcome_projection(limit=limit)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (OutcomeProjectionError, ValueError) as exc:
                payload = {"schema": "hes.trade_journal_outcomes_view.v1", "status": "BLOCKED",
                           "error": str(exc), "events": [], "count": 0,
                           "execution_enabled": False, "outcomes_inferred": False}
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/execution-journal":
            q = parse_qs(p.query)
            try:
                limit = int(q.get("limit", ["50"])[0])
                payload = configured_execution_journal(limit=limit)
                return self._send(200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
            except (ExecutionJournalProjectionError, ValueError) as exc:
                payload = {"schema": "hes.execution_journal_view.v1", "status": "BLOCKED",
                           "error": str(exc), "orders": [], "count": 0,
                           "read_only": True, "execution_enabled": False, "outcomes_inferred": False}
                return self._send(503, json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        if p.path == "/api/signal":
            q = parse_qs(p.query)
            symbol = q.get("symbol", ["BTCUSDT"])[0]
            interval = q.get("interval", ["15m"])[0]
            if symbol != "BTCUSDT" or interval != "15m":
                return self._send(400, b'{"error":"unsupported_signal_scope","decision":"NO_TRADE","execution_enabled":false}', "application/json")
            try:
                # Both timeframes come from the same canonical Binance Spot OHLCV source.
                batch, feature_result = _get_batch(symbol, interval)
                htf_batch, _ = _get_batch(symbol, "4h")
                strategy = _STRATEGY_PROVIDER.evaluate(
                    candles_15m=batch,
                    candles_4h=htf_batch,
                    now_ms=int(time.time() * 1000),
                    vwap=feature_result.snapshot.vwap if feature_result.snapshot is not None else None,
                )
                geometry = RiskGeometryV1(*strategy.risk_geometry) if strategy.risk_geometry else None
                result = _SIGNAL_AGENT.evaluate(
                    observed_at=strategy.observed_at,
                    venue=strategy.venue,
                    product=strategy.product,
                    symbol=strategy.symbol,
                    timeframe=strategy.timeframe,
                    regime=strategy.regime,
                    structure_labels=strategy.structure_labels,
                    structure_events=strategy.structure_events,
                    structure_direction=strategy.direction,
                    strategy_checks=strategy.strategy_checks,
                    confirmation_checks=strategy.confirmation_checks,
                    risk_checks=strategy.risk_checks,
                    risk_geometry=geometry,
                )
                blocked = list(strategy.blocked_reasons) + list(result.blocked_reasons)
                if not feature_result.decision_ready:
                    blocked.append("NATIVE_FEATURES_NOT_READY")
                if batch.gaps or htf_batch.gaps:
                    blocked.append("NATIVE_CANDLE_GAPS_PRESENT")

                # Adapt existing layer outputs into one auditable arbitration record.
                # The snapshot identity binds both source responses; no new indicators or policies.
                snapshot_sha = sha256((batch.response_sha256 + ":" + htf_batch.response_sha256).encode()).hexdigest()
                strategy_sha = (
                    result.strategy_quality.evidence_sha256
                    if result.strategy_quality and result.strategy_quality.evidence_sha256
                    else batch.response_sha256
                )
                structure_ok = strategy.direction in ("BULLISH", "BEARISH") and (
                    (strategy.direction == "BULLISH" and strategy.regime == "UPTREND")
                    or (strategy.direction == "BEARISH" and strategy.regime == "DOWNTREND")
                )
                source_blocked = any(
                    reason.startswith(("STRATEGY_SOURCE_STALE:", "STRATEGY_SOURCE_GAPS_PRESENT"))
                    for reason in strategy.blocked_reasons
                )
                data_ok = bool(feature_result.decision_ready and not batch.gaps and not htf_batch.gaps
                               and not source_blocked)
                confirmation_direction = (
                    "LONG" if getattr(result.confirmation, "state", "") == "CONFIRMED_LONG"
                    else "SHORT" if getattr(result.confirmation, "state", "") == "CONFIRMED_SHORT"
                    else strategy.direction
                )
                assessments = (
                    AgentAssessmentV1("data_quality", "native-feature-pipeline-v1", "PASS" if data_ok else "FAIL",
                        "NEUTRAL", strategy.venue, strategy.product, strategy.symbol, strategy.timeframe,
                        strategy.observed_at, snapshot_sha, batch.response_sha256,
                        () if data_ok else ("DATA_QUALITY_GATE_FAILED",)),
                    AgentAssessmentV1("market_structure", "market-structure-v1", "PASS" if structure_ok else "UNKNOWN",
                        strategy.direction, strategy.venue, strategy.product, strategy.symbol, strategy.timeframe,
                        strategy.observed_at, snapshot_sha, batch.response_sha256,
                        () if structure_ok else ("STRUCTURE_DIRECTION_OR_REGIME_UNKNOWN",)),
                    AgentAssessmentV1("strategy", result.strategy_quality.policy_version if result.strategy_quality else "unknown",
                        "PASS" if result.strategy_quality and result.strategy_quality.state == "PASS"
                        else "FAIL" if result.strategy_quality and result.strategy_quality.state == "FAIL" else "UNKNOWN",
                        strategy.direction, strategy.venue, strategy.product, strategy.symbol, strategy.timeframe,
                        strategy.observed_at, snapshot_sha, strategy_sha,
                        tuple(result.strategy_quality.reason_codes) if result.strategy_quality else ("STRATEGY_QUALITY_UNKNOWN",)),
                    AgentAssessmentV1("confirmation", "confirmation-policy-v1",
                        "PASS" if getattr(result.confirmation, "state", "") in ("CONFIRMED_LONG", "CONFIRMED_SHORT")
                        else "UNKNOWN",
                        confirmation_direction, strategy.venue, strategy.product, strategy.symbol, strategy.timeframe,
                        strategy.observed_at, snapshot_sha, batch.response_sha256,
                        tuple(getattr(result.confirmation, "reason_codes", ()))),
                    AgentAssessmentV1("risk", "risk-policy-v1",
                        "PASS" if getattr(result.risk, "state", "") == "RISK_APPROVED" else "FAIL",
                        confirmation_direction, strategy.venue, strategy.product, strategy.symbol, strategy.timeframe,
                        strategy.observed_at, snapshot_sha, batch.response_sha256,
                        tuple(getattr(result.risk, "reason_codes", ()))),
                )
                arbitration = _DISAGREEMENT_RESOLVER.resolve(
                    assessments=assessments, observed_at=datetime.now(timezone.utc)
                )
                if arbitration.decision == "NO_TRADE":
                    blocked.extend(arbitration.reason_codes)
                final_decision = arbitration.decision if not blocked else "NO_TRADE"
                payload = {
                    "status": "BLOCKED" if final_decision == "NO_TRADE" else "READY",
                    "agent_version": _SIGNAL_AGENT.VERSION,
                    "disagreement_resolver_version": _DISAGREEMENT_RESOLVER.VERSION,
                    "decision": final_decision,
                    "arbitration": arbitration.as_dict(),
                    "decision_reasons": list(arbitration.reason_codes),
                    "blocked_reasons": list(dict.fromkeys(blocked)),
                    "observed_at": strategy.observed_at.isoformat(),
                    "symbol": strategy.symbol,
                    "timeframe": strategy.timeframe,
                    "source": f"{strategy.venue}_native_ohlcv_v1",
                    "product": strategy.product,
                    "response_sha256": batch.response_sha256,
                    "htf_response_sha256": htf_batch.response_sha256,
                    "feature_ready": feature_result.decision_ready,
                    "feature_reason": feature_result.reason,
                    "feature_quality_passed": feature_result.quality.passed,
                    "strategy_quality_state": result.strategy_quality.state if result.strategy_quality else "UNKNOWN",
                    "strategy_quality_passed_count": result.strategy_quality.passed_count if result.strategy_quality else 0,
                    "strategy_quality_required_count": result.strategy_quality.required_count if result.strategy_quality else 5,
                    "strategy_policy_version": result.strategy_quality.policy_version if result.strategy_quality else "hes-strategy-policy-v1",
                    "strategy_evidence_sha256": result.strategy_quality.evidence_sha256 if result.strategy_quality else None,
                    "strategy_evidence_provider": _STRATEGY_PROVIDER.VERSION,
                    "structure_direction": strategy.direction,
                    "structure_regime": strategy.regime,
                    "mfi14": strategy.mfi14,
                    "mfi_divergence": strategy.mfi_divergence,
                    "adx14": strategy.adx14,
                    "plus_di14": strategy.plus_di14,
                    "minus_di14": strategy.minus_di14,
                    "ema50_15m": strategy.ema50_15m,
                    "ema50_4h": strategy.ema50_4h,
                    "ema200_4h": strategy.ema200_4h,
                    "order_block_version": strategy.order_block.version if strategy.order_block else "hes-order-block-context-v1",
                    "order_block_status": strategy.order_block.status if strategy.order_block else "UNAVAILABLE",
                    "order_block_score": strategy.order_block.score if strategy.order_block else None,
                    "order_block_max_score": strategy.order_block.max_score if strategy.order_block else 7,
                    "order_block_direction": strategy.order_block.direction if strategy.order_block else None,
                    "order_block_break_type": strategy.order_block.break_type if strategy.order_block else None,
                    "order_block_zone_low": str(strategy.order_block.zone_low) if strategy.order_block else None,
                    "order_block_zone_high": str(strategy.order_block.zone_high) if strategy.order_block else None,
                    "order_block_fresh": strategy.order_block.fresh if strategy.order_block else None,
                    "order_block_mitigated": strategy.order_block.mitigated if strategy.order_block else None,
                    "order_block_score_threshold_authorized": strategy.order_block.score_threshold_authorized if strategy.order_block else False,
                    "risk_state": result.risk.state,
                    "risk_reasons": list(result.risk.reason_codes),
                    "execution_enabled": False,
                    "execution_blocked_reasons": ["SYMBOL_MAPPING_EVIDENCE_MISSING", "LIVE_EXECUTION_DISABLED"],
                }
                # Forward learning is opt-in via an explicit durable journal path.
                # GET polling is idempotent: the journal keys the event by immutable
                # source hashes + policy version and rejects conflicting re-evaluations.
                learning_journal_path = os.environ.get("HES_FORWARD_LEARNING_DECISION_JOURNAL", "").strip()
                payload["learning_journal_status"] = "NOT_CONFIGURED"
                payload["learning_event_id"] = None
                if learning_journal_path:
                    if not payload["response_sha256"] or not payload["htf_response_sha256"]:
                        payload["learning_journal_status"] = "BLOCKED_MISSING_SOURCE_IDENTITY"
                    else:
                        if not data_ok:
                            rejected_at = "DATA_QUALITY"
                        elif not structure_ok:
                            rejected_at = "MARKET_STRUCTURE"
                        elif payload["strategy_quality_state"] != "PASS":
                            rejected_at = "STRATEGY_QUALITY"
                        elif getattr(result.confirmation, "state", "") not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
                            rejected_at = "CONFIRMATION"
                        elif getattr(result.risk, "state", "") != "RISK_APPROVED":
                            rejected_at = "RISK"
                        else:
                            rejected_at = ""
                        try:
                            journal_result = record_signal_decision(
                                learning_journal_path,
                                decision=final_decision,
                                observed_at=strategy.observed_at.isoformat(),
                                symbol=strategy.symbol,
                                timeframe=strategy.timeframe,
                                source=f"{strategy.venue}_native_ohlcv_v1",
                                product=strategy.product,
                                response_sha256=batch.response_sha256,
                                htf_response_sha256=htf_batch.response_sha256,
                                strategy_evidence_sha256=payload["strategy_evidence_sha256"],
                                policy_version=payload["strategy_policy_version"],
                                status=payload["status"],
                                market_regime=strategy.regime or "UNKNOWN",
                                rejected_at=rejected_at,
                                reason_codes=list(dict.fromkeys(blocked + list(arbitration.reason_codes))),
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
                    "execution_enabled": False,
                }).encode(), "application/json")
        if p.path!="/api/candles": return self._send(404,b'{"error":"not_found"}',"application/json")
        q=parse_qs(p.query); symbol=q.get("symbol",["BTCUSDT"])[0]; interval=q.get("interval",["1m"])[0]
        if symbol not in SUPPORTED_SYMBOLS or interval not in INTERVAL_MS:
            return self._send(400,b'{"error":"unsupported_symbol_or_interval"}',"application/json")
        try:
            # The exact same validated batch feeds the chart projection and feature pipeline.
            batch,feature_result=_get_batch(symbol,interval)
            now=datetime.now(timezone.utc); now_ms=int(now.timestamp()*1000); last=batch.candles[-1]
            age=(now_ms-last.close_time_ms)/1000
            payload={"status":"gaps_present" if batch.gaps else "ok",
                "source":"binance_native_ohlcv_v1","venue":batch.venue,"product":batch.product,
                "symbol":batch.symbol,"interval":batch.interval,"endpoint_kind":batch.endpoint_kind,
                "fetched_at_ms":batch.fetched_at_ms,"response_sha256":batch.response_sha256,
                "latest_age_seconds":age,"execution_enabled":False,
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
                "reason":type(exc).__name__,"fail_closed":True,"execution_enabled":False}).encode(),"application/json")
    def do_POST(self): return self._send(405,b'{"error":"method_not_allowed","execution_enabled":false}',"application/json")
    def log_message(self,fmt,*args):
        if os.environ.get("HES_DASHBOARD_ACCESS_LOG")=="1": super().log_message(fmt,*args)

def main():
    if os.environ.get("HES_BINANCE_STREAM_ENABLED", "0") == "1":
        _STREAM_STATE.update(status="starting", reason=None)
        Thread(target=_stream_worker, name="hes-binance-spot-kline", daemon=True).start()
    host=os.environ.get("HES_DASHBOARD_HOST","127.0.0.1"); port=int(os.environ.get("HES_DASHBOARD_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    print(f"HES read-only dashboard listening on http://{host}:{port}",flush=True); server.serve_forever()

if __name__=="__main__": main()
