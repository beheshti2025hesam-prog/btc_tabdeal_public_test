"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
import json, os, time
from urllib.parse import parse_qs, urlparse
from forward.native_ohlcv_v1 import INTERVAL_MS, validate_native_batch
from forward.native_ohlcv_gateio_v1 import GateioSpotKlineSource, SUPPORTED_INTERVALS
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.signal_agent_v1 import SignalAgentV1
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream

SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
CHART_ASSET_PATH = "/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js"
CHART_ASSET_FILE = Path(__file__).resolve().parent / "static" / "third_party" / "lightweight-charts" / "5.0.8" / "lightweight-charts.standalone.production.js"
_SOURCE = GateioSpotKlineSource()
_FEATURES = NativeOHLCVFeaturePipelineV1()
_SIGNAL_AGENT = SignalAgentV1(allowed_scopes=(("gateio", "spot", "BTCUSDT", "15m"),))
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
    ttl_ms = 75_000 if (symbol, interval) == ("BTCUSDT", "1m") else 15_000
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
</style><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><main><header><div><div class="brand">HES Trade Agent</div><div class="sub">Gate.io Spot · native closed candles</div></div><span class="pill">HOLD / NO_TRADE_ONLY</span></header>
<section class="panel"><div class="toolbar"><label>Symbol <select id="symbol"><option>BTCUSDT</option><option>ETHUSDT</option><option>SOLUSDT</option></select></label><label>Timeframe <select id="interval"><option>15m</option><option>1m</option><option>5m</option><option>1h</option><option>4h</option><option>1d</option></select></label><button id="refresh">Refresh data</button><span class="muted" id="source">Gate.io Spot public candles</span></div>
<div class="metrics"><div class="metric"><small>Last closed close</small><strong id="price">—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" style="font-size:14px">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume">—</strong></div><div class="metric"><small>Closed candles</small><strong id="count">—</strong></div></div>
<div class="panel" style="padding:8px;margin-top:14px"><div id="chart" role="img" aria-label="Candlestick chart"></div></div><div id="message" role="status">Loading validated closed candles…</div></section>
<section class="panel"><h3 style="margin-top:0">Signal Agent v1 · BTCUSDT / 15m</h3><div class="metrics"><div class="metric"><small>Decision</small><strong id="signalDecision">NO_TRADE</strong></div><div class="metric"><small>Agent status</small><strong id="signalStatus">Checking gates…</strong></div><div class="metric"><small>Feature quality</small><strong id="signalFeatureQuality">—</strong></div><div class="metric"><small>Strategy quality</small><strong id="signalStrategyQuality">UNKNOWN</strong></div><div class="metric"><small>Strategy quorum</small><strong id="signalStrategyQuorum">0/5</strong></div><div class="metric"><small>Order block score</small><strong id="signalOrderBlock">UNAVAILABLE</strong></div><div class="metric"><small>Risk gate</small><strong id="signalRisk">—</strong></div></div><p class="muted" id="signalReasons">Waiting for validated evidence…</p><div class="gate"><strong>Execution: disabled</strong><p class="muted">This is the read-only Signal Agent entry route. Missing symbol-mapping evidence, directional structure, strategy-level quality approval, risk geometry, or any risk approval keeps the decision at NO_TRADE. Feature-engine quality is descriptive and is not substituted for strategy-level signal quality.</p></div><div class="metrics"><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<section class="panel"><h3 style="margin-top:0">Decision and safety gates</h3><div class="gate"><strong>Execution: disabled</strong><p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<div class="footer">Charts powered by <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. Copyright (c) 2025 TradingView, Inc. Gate.io Spot is the source for this dashboard's reference candles; it is venue-specific, not a consolidated global feed. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Volume is shown as reported and is not normalized; its semantics are unverified. If the source is unavailable or stale, the chart fails closed.</div></main>
<script>
const $=id=>document.getElementById(id);let bars=[];let chart=null,candleSeries=null;
if(window.LightweightCharts){chart=LightweightCharts.createChart($('chart'),{autoSize:true,layout:{background:{type:'solid',color:'#121c2c'},textColor:'#91a2ba'},grid:{vertLines:{color:'#27364b'},horzLines:{color:'#27364b'}},rightPriceScale:{borderColor:'#27364b'},timeScale:{borderColor:'#27364b',timeVisible:true,secondsVisible:false},crosshair:{vertLine:{color:'#526783'},horzLine:{color:'#526783'}}});candleSeries=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#36c98f',downColor:'#f16b75',borderVisible:false,wickUpColor:'#36c98f',wickDownColor:'#f16b75'});}
function draw(){if(!candleSeries){$('message').textContent='FAIL CLOSED · chart library did not load; check network/CDN policy';return}candleSeries.setData(bars.map(b=>({time:Math.floor(b.open_time/1000),open:Number(b.open),high:Number(b.high),low:Number(b.low),close:Number(b.close)})));if(bars.length)chart.timeScale().fitContent()}
async function refresh(){const btn=$('refresh');btn.disabled=true;$('message').textContent='Fetching and validating closed reference candles…';try{const q=new URLSearchParams({symbol:$('symbol').value,interval:$('interval').value}),r=await fetch('/api/candles?'+q,{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Market data unavailable');bars=j.candles;if(!bars.length)throw Error('No closed candles returned');const b=bars[bars.length-1];$('price').textContent=Number(b.close).toLocaleString(undefined,{maximumFractionDigits:8});$('stamp').textContent=new Date(b.close_time).toISOString().replace('T',' ').replace('.000Z',' UTC');$('volume').textContent=b.volume;$('count').textContent=String(bars.length);$('source').textContent='Source: '+j.source+' · '+j.product+' · '+j.symbol;$('message').textContent='VALIDATED · '+(j.feature_ready?'FEATURES READY':'FEATURES GATED: '+j.feature_reason)+' · stream '+j.stream_status+(j.stream_reason?' ('+j.stream_reason+')':'')+' · latest age '+j.latest_age_seconds.toFixed(1)+'s · volume unchanged';draw()}catch(e){bars=[];draw();['price','stamp','volume','count'].forEach(k=>$(k).textContent='—');$('message').textContent='FAIL CLOSED · '+e.message}finally{btn.disabled=false}}
async function refreshSignal(){try{const q=new URLSearchParams({symbol:$('symbol').value,interval:$('interval').value}),r=await fetch('/api/signal?'+q,{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Signal evaluation unavailable');$('signalDecision').textContent=j.decision;$('signalStatus').textContent=j.status;$('signalFeatureQuality').textContent=j.feature_quality_passed===true?'PASS (descriptive)':j.feature_quality_passed===false?'FAIL':'UNKNOWN';$('signalStrategyQuality').textContent=j.strategy_quality_state||'UNKNOWN';$('signalStrategyQuorum').textContent=String(j.strategy_quality_passed_count??0)+'/'+String(j.strategy_quality_required_count??5);$('signalOrderBlock').textContent=j.order_block_score===null||j.order_block_score===undefined?'UNAVAILABLE':String(j.order_block_score)+'/'+String(j.order_block_max_score??7)+(j.order_block_fresh?' · FRESH':j.order_block_mitigated?' · MITIGATED':'');$('signalRisk').textContent=j.risk_state||'UNKNOWN';$('signalReasons').textContent=(j.blocked_reasons||[]).join(' · ')||'No block reasons supplied';}catch(e){$('signalDecision').textContent='NO_TRADE';$('signalStatus').textContent='BLOCKED';$('signalFeatureQuality').textContent='UNKNOWN';$('signalStrategyQuality').textContent='UNKNOWN';$('signalStrategyQuorum').textContent='0/5';$('signalOrderBlock').textContent='UNKNOWN';$('signalRisk').textContent='UNKNOWN';$('signalReasons').textContent='FAIL CLOSED · '+e.message}}
async function refreshBoth(){await refresh();await refreshSignal()} $('refresh').addEventListener('click',refreshBoth);$('symbol').addEventListener('change',refreshBoth);$('interval').addEventListener('change',refreshBoth);refreshBoth();setInterval(refreshBoth,15000);
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
        if p.path=="/healthz": return self._send(200,b'{"status":"ok","mode":"NO_TRADE_ONLY","execution_enabled":false,"source":"gateio_native_ohlcv_v1"}',"application/json")
        if p.path == "/api/signal":
            q = parse_qs(p.query)
            symbol = q.get("symbol", ["BTCUSDT"])[0]
            interval = q.get("interval", ["15m"])[0]
            if symbol != "BTCUSDT" or interval != "15m":
                return self._send(400, b'{"error":"unsupported_signal_scope","decision":"NO_TRADE","execution_enabled":false}', "application/json")
            try:
                # Reuse the canonical native batch/cache and feature result; no second data path.
                batch, feature_result = _get_batch(symbol, interval)
                observed_at = datetime.fromtimestamp(batch.fetched_at_ms / 1000, timezone.utc)
                evidence_ref = "native-ohlcv-sha256:" + batch.response_sha256
                # Unknown is deliberate until strategy-level providers are validated and wired.
                checks = (
                    ConfirmationCheck("structure_direction_aligned", "UNKNOWN", evidence_ref, observed_at),
                )
                result = _SIGNAL_AGENT.evaluate(
                    observed_at=observed_at,
                    venue=batch.venue,
                    product=batch.product,
                    symbol=batch.symbol,
                    timeframe=batch.interval,
                    regime="UNKNOWN",
                    structure_direction="UNKNOWN",
                    confirmation_checks=checks,
                    risk_checks=(),
                    risk_geometry=None,
                )
                blocked = list(result.blocked_reasons)
                blocked.extend((
                    "SYMBOL_MAPPING_EVIDENCE_MISSING",
                    "VALIDATED_STRUCTURE_PROVIDER_NOT_WIRED",
                    "STRATEGY_QUALITY_PROVIDER_NOT_WIRED",
                ))
                if not feature_result.decision_ready:
                    blocked.append("NATIVE_FEATURES_NOT_READY")
                if batch.gaps:
                    blocked.append("NATIVE_CANDLE_GAPS_PRESENT")
                payload = {
                    "status": "BLOCKED" if blocked else "NO_TRADE",
                    "agent_version": _SIGNAL_AGENT.VERSION,
                    "decision": "NO_TRADE",
                    "decision_reasons": list(result.decision.reason_codes),
                    "blocked_reasons": list(dict.fromkeys(blocked)),
                    "observed_at": observed_at.isoformat(),
                    "symbol": batch.symbol,
                    "timeframe": batch.interval,
                    "source": f"{batch.venue}_native_ohlcv_v1",
                    "product": batch.product,
                    "response_sha256": batch.response_sha256,
                    "feature_ready": feature_result.decision_ready,
                    "feature_reason": feature_result.reason,
                    "feature_quality_passed": feature_result.quality.passed,
                    "strategy_quality_state": result.strategy_quality.state if result.strategy_quality else "UNKNOWN",
                    "structure_direction": "UNKNOWN",
                    "risk_state": result.risk.state,
                    "risk_reasons": list(result.risk.reason_codes),
                    "execution_enabled": False,
                }
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
        if symbol not in SUPPORTED_SYMBOLS or interval not in SUPPORTED_INTERVALS or interval not in INTERVAL_MS:
            return self._send(400,b'{"error":"unsupported_symbol_or_interval"}',"application/json")
        try:
            # The exact same validated batch feeds the chart projection and feature pipeline.
            batch,feature_result=_get_batch(symbol,interval)
            now=datetime.now(timezone.utc); now_ms=int(now.timestamp()*1000); last=batch.candles[-1]
            age=(now_ms-last.close_time_ms)/1000
            payload={"status":"gaps_present" if batch.gaps else "ok",
                "source":"gateio_native_ohlcv_v1","venue":batch.venue,"product":batch.product,
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
    # The legacy Binance stream is deliberately not started by the Gate.io chart path.
    # Gate.io candles are REST-refreshed; a matching Gate.io stream needs its own
    # source-identity/reconciliation tests before it can be enabled.
    _STREAM_STATE.update(status="disabled", reason="gateio_stream_not_enabled")
    host=os.environ.get("HES_DASHBOARD_HOST","127.0.0.1"); port=int(os.environ.get("HES_DASHBOARD_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    print(f"HES read-only dashboard listening on http://{host}:{port}",flush=True); server.serve_forever()

if __name__=="__main__": main()
