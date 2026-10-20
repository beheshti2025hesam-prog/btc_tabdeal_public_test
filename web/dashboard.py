"""Integrated read-only HES dashboard; deliberately contains no order routes."""
from __future__ import annotations
from datetime import timedelta, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, os
from urllib.parse import parse_qs, urlparse
from forward.global_market_data_v1 import MarketDataError, fetch_closed_klines, INTERVALS

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HES Trade Agent</title><style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#121c2c;--line:#27364b;--muted:#91a2ba;--text:#e8eff8;--green:#36c98f;--red:#f16b75;--amber:#f2bf58}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:22px}
header,.toolbar,.metrics{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.brand{font-weight:750;font-size:22px}.sub,.muted{color:var(--muted);font-size:13px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:16px}.pill{border:1px solid #765e2e;color:var(--amber);padding:7px 10px;border-radius:999px;font-size:12px}
.metrics{justify-content:flex-start;margin-top:14px}.metric{min-width:150px;flex:1}.metric small{display:block;color:var(--muted)}.metric strong{font-size:20px;display:block;margin-top:5px}
.toolbar{justify-content:flex-start}button,select{background:#1b2a40;color:var(--text);border:1px solid #34465e;padding:9px 12px;border-radius:8px;font:inherit}button{cursor:pointer}canvas{display:block;width:100%;height:390px}
#message{color:var(--muted);font-size:13px;margin-top:10px}.gate{border-left:3px solid var(--amber);padding-left:12px}.footer{padding:18px 2px;color:var(--muted);font-size:12px;line-height:1.6}
@media(max-width:600px){main{padding:12px}canvas{height:300px}.metric{min-width:42%}}
</style></head><body><main><header><div><div class="brand">HES Trade Agent</div><div class="sub">Public USD reference · provider semantics unverified</div></div><span class="pill">HOLD / NO_TRADE_ONLY</span></header>
<section class="panel"><div class="toolbar"><label>Symbol <select id="symbol"><option>BTC-USD</option><option>ETH-USD</option><option>SOL-USD</option></select></label><label>Timeframe <select id="interval"><option>1m</option><option>5m</option><option>15m</option><option>60m</option><option>1d</option></select></label><button id="refresh">Refresh data</button><span class="muted" id="source">Public Yahoo USD reference · unverified</span></div>
<div class="metrics"><div class="metric"><small>Last closed close</small><strong id="price">—</strong></div><div class="metric"><small>Last closed candle (UTC)</small><strong id="stamp" style="font-size:14px">—</strong></div><div class="metric"><small>Source volume (unchanged)</small><strong id="volume">—</strong></div><div class="metric"><small>Closed candles</small><strong id="count">—</strong></div></div>
<div class="panel" style="padding:8px;margin-top:14px"><canvas id="chart" aria-label="Candlestick chart"></canvas></div><div id="message" role="status">Loading validated closed candles…</div></section>
<section class="panel"><h3 style="margin-top:0">Decision and safety gates</h3><div class="gate"><strong>Execution: disabled</strong><p class="muted">This dashboard has no order-submit route. A global chart price is not an executable venue quote. Symbol mapping, venue filters, spread/slippage, risk approval, idempotency and fill reconciliation must pass before a venue adapter can be enabled.</p></div><div class="metrics"><div class="metric"><small>Decision mode</small><strong>NO_TRADE_ONLY</strong></div><div class="metric"><small>Account access</small><strong>None</strong></div><div class="metric"><small>Order actions</small><strong>Disabled</strong></div></div></section>
<div class="footer">This public Yahoo USD reference feed is not certified as a global aggregate and is not approved for strategy decisions. Only fully closed, fresh, validated bars are displayed. Volume is shown as reported and is not normalized; its semantics are unverified. If the source is unavailable or stale, the chart fails closed.</div></main>
<script>
const $=id=>document.getElementById(id);let bars=[];
function draw(){const c=$('chart'),dpr=window.devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*dpr;c.height=h*dpr;const x=c.getContext('2d');x.scale(dpr,dpr);x.clearRect(0,0,w,h);if(!bars.length){x.fillStyle='#91a2ba';x.fillText('No validated closed candles available',18,30);return}const p={l:12,r:78,t:12,b:24},cw=w-p.l-p.r,ch=h-p.t-p.b,lo=Math.min(...bars.map(b=>+b.low)),hi=Math.max(...bars.map(b=>+b.high)),span=hi-lo||1,y=v=>p.t+(hi-v)/span*ch;x.strokeStyle='#27364b';x.fillStyle='#91a2ba';x.font='11px system-ui';for(let i=0;i<=4;i++){let v=hi-span*i/4,yy=y(v);x.beginPath();x.moveTo(p.l,yy);x.lineTo(w-p.r,yy);x.stroke();x.fillText(v.toLocaleString(undefined,{maximumFractionDigits:2}),w-p.r+6,yy+4)}const step=cw/bars.length,bw=Math.max(1,Math.min(9,step*.64));bars.forEach((b,i)=>{let xx=p.l+i*step+step/2,col=+b.close>=+b.open?'#36c98f':'#f16b75';x.strokeStyle=col;x.fillStyle=col;x.beginPath();x.moveTo(xx,y(+b.high));x.lineTo(xx,y(+b.low));x.stroke();let top=y(Math.max(+b.open,+b.close)),bot=y(Math.min(+b.open,+b.close));x.fillRect(xx-bw/2,top,bw,Math.max(1,bot-top))});x.fillStyle='#91a2ba';x.fillText(new Date(bars[0].open_time).toLocaleTimeString(),p.l,h-6);x.fillText(new Date(bars[bars.length-1].open_time).toLocaleTimeString(),Math.max(p.l,w-p.r-60),h-6)}
async function refresh(){const btn=$('refresh');btn.disabled=true;$('message').textContent='Fetching and validating closed reference candles…';try{const q=new URLSearchParams({symbol:$('symbol').value,interval:$('interval').value}),r=await fetch('/api/candles?'+q,{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Market data unavailable');bars=j.candles;if(!bars.length)throw Error('No closed candles returned');const b=bars[bars.length-1];$('price').textContent=Number(b.close).toLocaleString(undefined,{maximumFractionDigits:8});$('stamp').textContent=new Date(b.close_time).toISOString().replace('T',' ').replace('.000Z',' UTC');$('volume').textContent=b.volume;$('count').textContent=String(bars.length);$('source').textContent='Source: '+j.source+' · '+j.market+' · '+j.symbol;$('message').textContent='PASS · reference bars validated · latest age '+j.latest_age_seconds.toFixed(1)+'s · volume preserved';draw()}catch(e){bars=[];draw();['price','stamp','volume','count'].forEach(k=>$(k).textContent='—');$('message').textContent='FAIL CLOSED · '+e.message}finally{btn.disabled=false}}
$('refresh').addEventListener('click',refresh);$('symbol').addEventListener('change',refresh);$('interval').addEventListener('change',refresh);window.addEventListener('resize',draw);refresh();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version = "HESReadOnlyDashboard/1.0"
    def _send(self,status,body,content_type):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/": return self._send(200,HTML.encode(),"text/html; charset=utf-8")
        if p.path=="/healthz": return self._send(200,b'{"status":"ok","mode":"NO_TRADE_ONLY","execution_enabled":false}',"application/json")
        if p.path!="/api/candles": return self._send(404,b'{"error":"not_found"}',"application/json")
        q=parse_qs(p.query); symbol=q.get("symbol",["BTC-USD"])[0]; interval=q.get("interval",["1m"])[0]
        if symbol not in {"BTC-USD","ETH-USD","SOL-USD"} or interval not in INTERVALS:
            return self._send(400,b'{"error":"unsupported_symbol_or_interval"}',"application/json")
        try:
            candles=fetch_closed_klines(symbol=symbol,interval=interval,limit=240,
                max_latest_age=timedelta(seconds=max(180,INTERVALS[interval][0]*2)))
            now=datetime.now(timezone.utc); last=candles[-1]
            payload={"status":"ok","source":last.source,"market":last.market,"symbol":symbol,"interval":interval,
                "latest_age_seconds":(now-last.close_time).total_seconds(),"execution_enabled":False,
                "candles":[{"open_time":int(c.open_time.timestamp()*1000),"close_time":c.close_time.isoformat(),
                    "open":str(c.open),"high":str(c.high),"low":str(c.low),"close":str(c.close),"volume":str(c.volume)} for c in candles]}
            return self._send(200,json.dumps(payload,separators=(",",":")).encode(),"application/json")
        except MarketDataError as exc:
            return self._send(503,json.dumps({"error":str(exc),"fail_closed":True}).encode(),"application/json")
    def do_POST(self): return self._send(405,b'{"error":"method_not_allowed","execution_enabled":false}',"application/json")
    def log_message(self,fmt,*args):
        if os.environ.get("HES_DASHBOARD_ACCESS_LOG")=="1": super().log_message(fmt,*args)

def main():
    host=os.environ.get("HES_DASHBOARD_HOST","127.0.0.1"); port=int(os.environ.get("HES_DASHBOARD_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    print(f"HES read-only dashboard listening on http://{host}:{port}",flush=True); server.serve_forever()

if __name__=="__main__": main()
