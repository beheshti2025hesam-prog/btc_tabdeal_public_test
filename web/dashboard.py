"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
import json, os, time
from urllib.parse import parse_qs, urlparse
from forward.native_ohlcv_v1 import BinanceSpotKlineSource, INTERVAL_MS, validate_native_batch
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event, assert_event_matches_batch
from forward.native_ohlcv_stream_transport_v1 import run_spot_kline_stream

SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
CHART_ASSET_PATH = "/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js"
CHART_ASSET_FILE = Path(__file__).resolve().parent / "static" / "third_party" / "lightweight-charts" / "5.0.8" / "lightweight-charts.standalone.production.js"
_SOURCE = BinanceSpotKlineSource()
_FEATURES = NativeOHLCVFeaturePipelineV1()
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
<title>HES Trade Agent · Market Command Center</title><style>
:root{color-scheme:dark;--bg:#080e19;--panel:#101a2a;--panel-2:#142238;--line:#26364d;--muted:#9aaac0;--text:#edf3fb;--green:#45d6a0;--red:#ff7b85;--amber:#f4c66a;--focus:#80b7ff}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 12% -10%,#182944 0,transparent 42%),var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1280px;margin:auto;padding:26px}
header,.toolbar,.metrics,.section-head,.header-actions{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.brand{font-weight:780;font-size:24px;letter-spacing:-.5px}.brand-mark{display:inline-grid;place-items:center;width:36px;height:36px;margin-right:10px;border-radius:11px;background:linear-gradient(145deg,#245b53,#193b50);color:#8af0c7;font-weight:850;vertical-align:middle}.sub,.muted{color:var(--muted);font-size:13px}.eyebrow{color:#8ca5c4;text-transform:uppercase;letter-spacing:1.4px;font-size:10px;font-weight:800}.skip-link{position:absolute;left:-9999px;top:8px;background:var(--text);color:var(--bg);padding:10px;z-index:10}.skip-link:focus{left:8px}
.panel{background:linear-gradient(160deg,rgba(20,34,54,.98),rgba(14,24,39,.98));border:1px solid var(--line);border-radius:16px;padding:20px;margin-top:18px;box-shadow:0 12px 32px #00000017}.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid #7d6334;background:#3a2e1a55;color:var(--amber);padding:7px 11px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.35px}.dot{width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block}.section-head{align-items:flex-start;margin-bottom:16px}.section-head h2,.section-head h3{margin:3px 0 0;font-size:17px;letter-spacing:-.2px}.section-head p{margin:3px 0 0}
.metrics{justify-content:flex-start;margin-top:18px;gap:10px}.metric{min-width:145px;flex:1;background:#0b1422a8;border:1px solid #27364b;border-radius:12px;padding:14px 15px;min-height:94px}.metric small{display:block;color:var(--muted);font-size:12px}.metric strong{font-size:21px;display:block;margin-top:8px;letter-spacing:-.4px;overflow-wrap:anywhere}.metric .positive{color:var(--green)}
.toolbar{justify-content:flex-start;gap:14px;padding:14px;background:#0a1321;border:1px solid #26364d;border-radius:12px}.control{display:grid;gap:5px;color:#b9c8db;font-size:12px;font-weight:650}button,select{background:#17263b;color:var(--text);border:1px solid #3a4d68;padding:10px 13px;border-radius:9px;font:inherit;min-height:42px}select{min-width:100px}button{cursor:pointer;font-weight:700;transition:background .15s,border-color .15s,transform .15s}button:hover:not(:disabled){background:#223753;border-color:#6a86aa}button:active:not(:disabled){transform:translateY(1px)}button:disabled{opacity:.55;cursor:wait}button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--focus);outline-offset:3px}.primary{background:#1c5549;border-color:#2b816c}.primary:hover:not(:disabled){background:#246b5b}.toolbar .spacer{flex:1}#chart{display:block;width:100%;height:390px}.chart-shell{padding:8px;background:#0b1421;border:1px solid #26364d;border-radius:12px;margin-top:16px}
#message{display:flex;align-items:flex-start;gap:9px;color:var(--muted);font-size:13px;margin-top:13px;min-height:24px}.message-dot{flex:0 0 8px;height:8px;border-radius:50%;background:#8ca5c4;margin-top:6px}.message-ok .message-dot{background:var(--green)}.message-error{color:#ff9da4!important}.message-error .message-dot{background:var(--red)}.gate{border-left:3px solid var(--amber);padding:4px 0 4px 14px}.gate strong{display:flex;align-items:center;gap:8px}.gate p{max-width:900px;line-height:1.65}.safety-grid .metric{min-height:82px}.safety-grid .metric strong{font-size:15px}.switch{display:inline-flex;gap:8px;align-items:center;color:var(--muted);font-size:12px}.switch input{accent-color:var(--green);width:16px;height:16px}.footer{padding:22px 2px;color:var(--muted);font-size:12px;line-height:1.7}.footer a{color:#9dc5ff}.divider{height:1px;background:var(--line);margin:18px 0}.chart-legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px}.legend-key{display:inline-flex;align-items:center;gap:6px}.legend-key i{width:8px;height:8px;border-radius:2px;display:inline-block}.last-update{font-variant-numeric:tabular-nums}
@media(max-width:760px){main{padding:14px}.panel{padding:14px;margin-top:12px}.brand{font-size:20px}.metric{min-width:calc(50% - 8px);padding:12px;min-height:86px}.metric strong{font-size:18px}.toolbar{gap:10px}.toolbar .control{flex:1;min-width:calc(50% - 8px)}.toolbar button{flex:1}#chart{height:320px}.header-actions{width:100%;justify-content:space-between}}
@media(max-width:390px){main{padding:10px}.metric{min-width:100%}.toolbar .control{min-width:100%}#chart{height:280px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition:none!important;animation:none!important}}
</style><script src="/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js" integrity="sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl" crossorigin="anonymous"></script></head><body><a class="skip-link" href="#market">Skip to market dashboard</a><main><header><div><div class="brand"><span class="brand-mark" aria-hidden="true">H</span>HES Trade Agent</div><div class="sub">Market command center <span aria-hidden="true">·</span> Read-only monitoring</div></div><div class="header-actions"><span class="pill"><span class="dot" aria-hidden="true"></span> HOLD / NO_TRADE_ONLY</span></div></header>
<section class="panel" id="market" aria-labelledby="market-title"><div class="section-head"><div><div class="eyebrow">Market overview</div><h2 id="market-title">Price action</h2><p class="muted">Only validated, fully closed candles are shown.</p></div><div class="muted last-update" id="updated">Last update: —</div></div><div class="toolbar"><label class="control">Market symbol <select id="symbol"><option>BTCUSDT</option><option>ETHUSDT</option><option>SOLUSDT</option></select></label><label class="control">Timeframe <select id="interval"><option>1m</option><option>5m</option><option>15m</option><option>1h</option><option>1d</option></select></label><button class="primary" id="refresh" type="button"><span aria-hidden="true">↻</span> Refresh data</button><label class="switch"><input id="auto-refresh" type="checkbox" checked> Auto-refresh · 15s</label><span class="spacer"></span><span class="muted" id="source">Binance Spot public klines</span></div>
<div class="metrics" aria-label="Market data summary"><div class="metric"><small>Last closed price</small><strong id="price">—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" style="font-size:14px">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume">—</strong></div><div class="metric"><small>Closed candles</small><strong id="count">—</strong></div></div>
<div class="chart-shell"><div class="chart-legend"><span class="legend-key"><i style="background:var(--green)"></i> Candle closed higher</span><span class="legend-key"><i style="background:var(--red)"></i> Candle closed lower</span><span class="legend-key">Time displayed in UTC</span></div><div id="chart" role="img" aria-label="Interactive candlestick price chart"></div></div><div id="message" role="status" aria-live="polite" aria-atomic="true"><span class="message-dot" aria-hidden="true"></span><span id="message-text">Loading validated closed candles…</span></div></section>
<section class="panel" aria-labelledby="safety-title"><div class="section-head"><div><div class="eyebrow">Risk boundary</div><h2 id="safety-title">Decision &amp; safety gates</h2><p class="muted">Market observation does not authorize a trading decision.</p></div></div><div class="gate"><strong><span class="dot" style="color:var(--amber)" aria-hidden="true"></span> Execution disabled<p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics safety-grid"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<div class="footer"><div class="divider"></div><strong>Data &amp; execution policy</strong><br>Charts powered by <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a>. Copyright (c) 2025 TradingView, Inc. Binance Spot is venue-specific, not a consolidated global feed. It is read-only; feature output is descriptive and does not authorize strategy or execution. Only fully closed, fresh, validated bars are displayed. Volume is shown as reported and is not normalized; its semantics are unverified. If the source is unavailable or stale, the chart fails closed.</div></main>
<script>
const $=id=>document.getElementById(id);let bars=[];let chart=null,candleSeries=null;let refreshTimer=null;let inFlight=false;
if(window.LightweightCharts){chart=LightweightCharts.createChart($('chart'),{autoSize:true,layout:{background:{type:'solid',color:'#121c2c'},textColor:'#91a2ba'},grid:{vertLines:{color:'#27364b'},horzLines:{color:'#27364b'}},rightPriceScale:{borderColor:'#27364b'},timeScale:{borderColor:'#27364b',timeVisible:true,secondsVisible:false},crosshair:{vertLine:{color:'#526783'},horzLine:{color:'#526783'}}});candleSeries=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#36c98f',downColor:'#f16b75',borderVisible:false,wickUpColor:'#36c98f',wickDownColor:'#f16b75'});}
function setMessage(text,state='info'){const box=$('message');box.className=state==='error'?'message-error':state==='ok'?'message-ok':'';$('message-text').textContent=text}
function draw(){if(!candleSeries){setMessage('FAIL CLOSED · chart library did not load. No chart data is displayed.','error');return}candleSeries.setData(bars.map(b=>({time:Math.floor(b.open_time/1000),open:Number(b.open),high:Number(b.high),low:Number(b.low),close:Number(b.close)})));if(bars.length)chart.timeScale().fitContent()}
async function refresh(){if(inFlight)return;inFlight=true;const btn=$('refresh');btn.disabled=true;btn.setAttribute('aria-busy','true');setMessage('Fetching and validating closed reference candles…');try{const q=new URLSearchParams({symbol:$('symbol').value,interval:$('interval').value}),r=await fetch('/api/candles?'+q,{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Market data unavailable');bars=j.candles;if(!bars.length)throw Error('No closed candles returned');const b=bars[bars.length-1];$('price').textContent=Number(b.close).toLocaleString(undefined,{maximumFractionDigits:8});$('stamp').textContent=new Date(b.close_time).toISOString().replace('T',' ').replace('.000Z',' UTC');$('volume').textContent=b.volume;$('count').textContent=String(bars.length);$('source').textContent='Source: '+j.source+' · '+j.product+' · '+j.symbol;$('updated').textContent='Last update: '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});setMessage('VALIDATED · '+(j.feature_ready?'FEATURES READY':'FEATURES GATED: '+j.feature_reason)+' · stream '+j.stream_status+(j.stream_reason?' ('+j.stream_reason+')':'')+' · latest age '+j.latest_age_seconds.toFixed(1)+'s · volume unchanged','ok');draw()}catch(e){bars=[];draw();['price','stamp','volume','count'].forEach(k=>$(k).textContent='—');setMessage('FAIL CLOSED · '+e.message,'error');$('updated').textContent='Last successful update: unavailable'}finally{btn.disabled=false;btn.removeAttribute('aria-busy');inFlight=false}}
$('refresh').addEventListener('click',refresh);$('symbol').addEventListener('change',refresh);$('interval').addEventListener('change',refresh);function scheduleRefresh(){if(refreshTimer)clearInterval(refreshTimer);refreshTimer=null;if($('auto-refresh').checked)refreshTimer=setInterval(refresh,15000)}$('auto-refresh').addEventListener('change',scheduleRefresh);scheduleRefresh();refresh();
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
