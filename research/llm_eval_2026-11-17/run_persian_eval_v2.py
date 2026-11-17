from pathlib import Path
import json, hashlib, sys, importlib.util
from datetime import datetime, timezone
PROJECT=Path(__file__).resolve().parents[2]
CANDIDATE=PROJECT
if not (CANDIDATE/"web/mother_chat_v1.py").is_file():
    CANDIDATE=PROJECT/"forward/hoshyar-integration-worktree"
MODULE=CANDIDATE/"web/mother_chat_v1.py"
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("hes_mother_chat_eval",MODULE)
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
SUITE=json.loads((OUT/"persian_test_suite_v2.json").read_text(encoding="utf-8"))
trace="a"*64
payloads={
"FA-01":{"mother":{"status":"BLOCKED_GATE","decision":"NO_TRADE","trace_id":trace,"audit_sha256":"b"*64,"reason_codes":["NO_CONFIRMED_20_BAR_BREAKOUT","PRICE_NOT_ALIGNED_WITH_EMA50_AND_VWAP","MOMENTUM_OR_FLOW_NOT_CONFIRMED"],"stages":[{"agent":"confirmation","state":"BLOCKED","reason_codes":["CONFIRMATION_UNCONFIRMED"]},{"agent":"risk","state":"BLOCKED","reason_codes":["RISK_REJECTED"]}],"witness":{"verified":True}},"strategy":{"status":"VERIFIED","report_sha256":"c"*64},"trace_id":trace,"evidence_refs":["mother:"+trace,"strategy:"+"c"*64]},
"FA-02":{"mother":{"status":"BLOCKED_GATE","decision":"NO_TRADE","trace_id":trace,"audit_sha256":"b"*64,"reason_codes":["NO_TRADE"],"stages":[],"witness":{"verified":True}},"strategy":{"status":"VERIFIED","report_sha256":"c"*64},"news":{"monitor":{"status":"OK"}},"trace_id":trace,"evidence_refs":["mother:"+trace]},
"FA-03":{"strategy":{"market_regime":"RANGE","decision":"NO_TRADE","report_sha256":"d"*64},"latest_candle":{"close":"TEST_FIXTURE_CLOSE","age_seconds":60},"trace_id":trace,"evidence_refs":["market-fixture:"+trace]},
"FA-04":{"journal":{"status":"VERIFIED","decision_count":96},"strategy":{},"trace_id":trace,"evidence_refs":["journal-fixture:"+trace]},
"FA-05":{"news":{"monitor":{"status":"OK","source_profile_status":"incomplete","source_health":[{"name":"test-source","status":"OK"}]},"brief":{"findings":[]}},"trace_id":trace,"evidence_refs":["news-fixture:"+trace]},
"FA-06":{"components":{"mother":{"status":"BLOCKED_GATE","reason":"NO_TRADE"},"strategy":{"status":"VERIFIED"},"journal":{"status":"VERIFIED"}},"trace_id":trace,"evidence_refs":["diagnostics-fixture:"+trace]}}
results=[]
for c in SUITE["cases"]:
 calls=[]; readers={}
 if c["id"] not in ("FA-07","FA-08"):
  def factory(case_id):
   def read(): calls.append(case_id); return payloads[case_id]
   return read
  readers[c["expected_intent"]]=factory(c["id"])
 r=mod.build_chat_response(c["prompt"],readers,now=1794924000)
 checks={}
 for check in c["checks"]:
  if check=="execution_disabled": checks[check]=all(r[k] is False for k in ("external_llm_used","execution_enabled","orders_placed","journal_write","policy_mutation"))
  elif check=="no_reader_called": checks[check]=not calls
  else: checks[check]=check in r["answer"]
 ok=r["intent"]==c["expected_intent"] and r["status"]==c["expected_status"] and r["language"]=="fa" and r["direction"]=="rtl" and all(checks.values())
 results.append({"id":c["id"],"category":c["category"],"prompt":c["prompt"],"actual_intent":r["intent"],"actual_status":r["status"],"language":r["language"],"direction":r["direction"],"answer":r["answer"],"claims":r["claims"],"uncertainties":r["uncertainties"],"evidence_refs":r["evidence_refs"],"safety_flags":{k:r[k] for k in ("external_llm_used","execution_enabled","orders_placed","journal_write","policy_mutation")},"reader_calls":calls,"checks":checks,"pass":ok})
res={"benchmark_id":SUITE["benchmark_id"],"created_at_utc":datetime.now(timezone.utc).isoformat(),"execution_mode":"deterministic Mother Chat candidate with synthetic fixtures","not_live_market_data":True,"not_llm_inference":True,"source_module_sha256":hashlib.sha256(MODULE.read_bytes()).hexdigest(),"cases_total":len(results),"cases_passed":sum(x["pass"] for x in results),"cases_failed":sum(not x["pass"] for x in results),"all_persian_rtl":all(x["language"]=="fa" and x["direction"]=="rtl" for x in results),"all_safety_flags_fail_closed":all(not any(x["safety_flags"].values()) for x in results),"results":results}
(OUT/"DETERMINISTIC_MOTHER_CHAT_RESULTS_v2.json").write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("PERSIAN",res["cases_passed"],"/",res["cases_total"],"PASS")
print("RTL",res["all_persian_rtl"],"SAFETY",res["all_safety_flags_fail_closed"])
for x in results: print(x["id"],x["actual_intent"],x["actual_status"],"PASS" if x["pass"] else "FAIL")
if res["cases_failed"]: raise SystemExit(1)
