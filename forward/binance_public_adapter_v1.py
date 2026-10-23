"""Read-only Binance public Spot kline adapter with provenance; no order APIs."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL="https://api.binance.com"
INTERVALS={"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"}
@dataclass(frozen=True)
class Candle:
    symbol:str; interval:str; open_time_ms:int; close_time_ms:int
    open:str; high:str; low:str; close:str; volume:str; quote_volume:str; trade_count:int; closed:bool
@dataclass(frozen=True)
class AdapterResult:
    status:str; source:str; endpoint:str; symbol:str; interval:str; received_at_utc:str
    http_status:int|None; raw_sha256:str|None; raw_bytes:int; candles:tuple[Candle,...]; reason_code:str|None=None

def fetch_closed_klines(symbol="BTCUSDT",interval="15m",limit=100,*,base_url=BASE_URL,timeout=8.0,now_ms=None,opener=urlopen):
    symbol=symbol.upper()
    if not symbol.isalnum() or not 1<=len(symbol)<=30: raise ValueError("INVALID_SYMBOL")
    if interval not in INTERVALS: raise ValueError("INVALID_INTERVAL")
    if not 1<=limit<=1000: raise ValueError("INVALID_LIMIT")
    endpoint=base_url.rstrip("/")+"/api/v3/klines?"+urlencode({"symbol":symbol,"interval":interval,"limit":limit})
    received=datetime.now(timezone.utc)
    stamp=lambda:datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
    try:
        with opener(Request(endpoint,headers={"Accept":"application/json","User-Agent":"HES-Trade-Agent/1.0"}),timeout=timeout) as response:
            status=getattr(response,"status",200); raw=response.read()
        received=datetime.now(timezone.utc)
    except HTTPError as e:
        return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,stamp(),e.code,None,0,(),"HTTP_ERROR")
    except (URLError,TimeoutError,OSError):
        return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,stamp(),None,None,0,(),"NETWORK_ERROR")
    received_text=received.isoformat(timespec="milliseconds").replace("+00:00","Z")
    digest=sha256(raw).hexdigest()
    try: payload=json.loads(raw)
    except (json.JSONDecodeError,UnicodeDecodeError):
        return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,received_text,status,digest,len(raw),(),"INVALID_JSON")
    if status!=200 or not isinstance(payload,list):
        return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,received_text,status,digest,len(raw),(),"INVALID_RESPONSE_SHAPE")
    now=now_ms() if now_ms else int(time.time()*1000); candles=[]; prev=-1
    try:
        for item in payload:
            if not isinstance(item,list) or len(item)<11: raise ValueError()
            op,cl=int(item[0]),int(item[6])
            if op<=prev: raise ValueError()
            prev=op
            o,h,l,c,v,q=map(str,(item[1],item[2],item[3],item[4],item[5],item[7]))
            if float(h)<max(float(o),float(c)) or float(l)>min(float(o),float(c)) or float(l)>float(h): raise ValueError()
            candles.append(Candle(symbol,interval,op,cl,o,h,l,v,q,int(item[8]),cl<now))
    except (ValueError,TypeError,IndexError):
        return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,received_text,status,digest,len(raw),(),"INVALID_CANDLE_DATA")
    closed=tuple(c for c in candles if c.closed)
    if not closed: return AdapterResult("BLOCKED","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,received_text,status,digest,len(raw),(),"NO_CLOSED_CANDLES")
    return AdapterResult("OK","BINANCE_SPOT_PUBLIC",endpoint,symbol,interval,received_text,status,digest,len(raw),closed)
def result_json(result): return json.dumps(asdict(result),sort_keys=True,separators=(",",":"),ensure_ascii=False)
