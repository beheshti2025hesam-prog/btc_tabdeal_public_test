#!/usr/bin/env python3
"""Per-run 24h read-only feed soak with freshness and service gates."""
import fcntl, json, math, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path('/opt/hes-trade-agent')
sys.path.insert(0,str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input
SERVICES=('hes-global-market-data-gateio.service','hes-global-market-data-gateio-1h.service','hes-global-market-data-gateio-4h.service')
TIMEFRAME_SECONDS={'15m':900,'1h':3600,'4h':14400}
GRACE_SECONDS=180
DURATION=24*60*60
INTERVAL=60
LOG=ROOT/'data/forward/gateio_feed_soak_24h_v2.jsonl'
def sample(seq,start):
 rec={'schema':'hes_gateio_soak_sample_v2','sample':seq,'observed_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':int(time.monotonic()-start)}
 try:
  data=load_market_input(root=ROOT)
  rec['source']=data.get('source'); rec['symbol']=data.get('symbol')
  if rec['source']!='gateio_public_spot' or rec['symbol']!='BTC_USDT': raise ValueError('UNEXPECTED_SOURCE_OR_SYMBOL')
  details={}
  for tf,period in TIMEFRAME_SECONDS.items():
   rows=data['timeframes'].get(tf,[])
   if not rows: raise ValueError('NO_BARS_'+tf)
   row=rows[-1]; close_time=int(row['close_time']); age=int(time.time()-close_time)
   close=float(row['close'])
   if not math.isfinite(close) or close<=0: raise ValueError('INVALID_CLOSE_'+tf)
   if age < -GRACE_SECONDS or age > period+GRACE_SECONDS: raise ValueError('STALE_OR_FUTURE_CANDLE_'+tf+':age='+str(age))
   details[tf]={'bars':len(rows),'last_close_time':close_time,'age_seconds':age,'close':close}
  rec['timeframes']=details
  states={}
  for svc in SERVICES:
   q=subprocess.run(['systemctl','is-active',svc],capture_output=True,text=True,timeout=5)
   states[svc]=q.stdout.strip() if q.returncode==0 else 'INACTIVE'
  rec['services']=states
  if not all(v=='active' for v in states.values()): raise ValueError('SERVICE_NOT_ACTIVE')
  rec['ok']=True
 except Exception as e:
  rec['ok']=False; rec['error']=type(e).__name__+':'+str(e)[:300]
 return rec
def main():
 LOG.parent.mkdir(parents=True,exist_ok=True)
 lock_handle=(LOG.parent/'.gateio_feed_soak_v2.lock').open('a',encoding='utf-8')
 try:
  fcntl.flock(lock_handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print(json.dumps({'schema':'hes_gateio_soak_error_v1','error':'SOAK_ALREADY_RUNNING','ok':False}),flush=True)
  return 4
 start=time.monotonic(); deadline=start+DURATION; seq=0
 while True:
  seq+=1; rec=sample(seq,start)
  with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps(rec,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
  print(json.dumps(rec,sort_keys=True),flush=True)
  if not rec['ok']: return 2
  if os.environ.get('HES_SOAK_ONCE')=='1': return 0
  if time.monotonic()>=deadline: break
  time.sleep(min(INTERVAL,max(0,deadline-time.monotonic())))
 summary={'schema':'hes_gateio_soak_summary_v2','finished_at':datetime.now(timezone.utc).isoformat(),'samples':seq,'duration_seconds':int(time.monotonic()-start),'passed':seq>=1400 and int(time.monotonic()-start)>=DURATION}
 with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps(summary,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
 print(json.dumps(summary),flush=True)
 return 0 if summary['passed'] else 3
if __name__=='__main__': raise SystemExit(main())
