#!/usr/bin/env python3
"""Non-trading 24h Gate.io feed soak. Logs one validated health sample per minute."""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path("/opt/hes-trade-agent")
sys.path.insert(0,str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input
SERVICES=("hes-global-market-data-gateio.service","hes-global-market-data-gateio-1h.service","hes-global-market-data-gateio-4h.service")
DURATION=24*60*60
INTERVAL=60
LOG=ROOT/"data/forward/gateio_feed_soak_24h_v1.jsonl"
def main():
 start=time.monotonic(); deadline=start+DURATION; seq=0
 LOG.parent.mkdir(parents=True,exist_ok=True)
 while time.monotonic()<deadline:
  seq+=1; now=datetime.now(timezone.utc).isoformat(); record={"schema":"hes_gateio_soak_sample_v1","sample":seq,"observed_at":now,"elapsed_seconds":int(time.monotonic()-start)}
  try:
   data=load_market_input(root=ROOT)
   record["source"]=data["source"]; record["symbol"]=data["symbol"]
   record["timeframes"]={tf:{"bars":len(rows),"last_close_time":int(rows[-1]["close_time"]),"age_seconds":int(time.time()-int(rows[-1]["close_time"]))} for tf,rows in data["timeframes"].items()}
   states={}
   for svc in SERVICES:
    q=subprocess.run(["systemctl","is-active",svc],capture_output=True,text=True,timeout=5)
    states[svc]=q.stdout.strip() if q.returncode==0 else "INACTIVE"
   record["services"]=states
   record["ok"]=all(v=="active" for v in states.values())
   if not record["ok"]: record["error"]="SERVICE_NOT_ACTIVE"
  except Exception as exc:
   record["ok"]=False; record["error"]=type(exc).__name__+":"+str(exc)[:300]
  with LOG.open("a",encoding="utf-8") as f:
   f.write(json.dumps(record,sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())
  print(json.dumps(record),flush=True)
  if not record["ok"]:
   # Preserve failure evidence and stop; never convert an unhealthy run into a pass.
   return 2
  time.sleep(min(INTERVAL,max(0,deadline-time.monotonic())))
 final={"schema":"hes_gateio_soak_summary_v1","finished_at":datetime.now(timezone.utc).isoformat(),"samples":seq,"duration_seconds":int(time.monotonic()-start),"passed":seq>=1400}
 with LOG.open("a",encoding="utf-8") as f: f.write(json.dumps(final,sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())
 return 0 if final["passed"] else 3
if __name__=="__main__": raise SystemExit(main())
