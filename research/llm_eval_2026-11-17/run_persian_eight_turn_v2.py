from __future__ import annotations
import hashlib, json, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
choices=[PROJECT, PROJECT/"candidates/persian-eval-mainline-snapshot-20261117", PROJECT/"forward/hoshyar-integration-worktree"]
SOURCE=next((p for p in choices if (p/"web/hoshyar_local_v1.py").is_file()),None)
if SOURCE is None: raise SystemExit("HES_ASSISTANT_SOURCE_NOT_FOUND")
sys.path.insert(0,str(SOURCE))
from web.hoshyar_local_v1 import HoshyarConversationMemoryV1,HoshyarLocalAssistantV1

class NeverCallLocalModel:
    def route_intent(self,messages): raise AssertionError("local model route called for supported Persian request")
    def general_answer(self,messages): raise AssertionError("local model answer called for deterministic Persian request")

trace="e"*64
mother={"status":"BLOCKED_GATE","decision":"NO_TRADE","trace_id":trace,"audit_sha256":"f"*64,"reason_codes":["NO_CONFIRMED_20_BAR_BREAKOUT","PRICE_NOT_ALIGNED_WITH_EMA50_AND_VWAP","MOMENTUM_OR_FLOW_NOT_CONFIRMED"],"stages":[{"agent":"confirmation","state":"BLOCKED","reason_codes":["CONFIRMATION_UNCONFIRMED"]},{"agent":"risk","state":"BLOCKED","reason_codes":["RISK_REJECTED"]}],"witness":{"verified":True}}
strategy={"status":"VERIFIED","report_sha256":"a"*64,"market_regime":"RANGE","decision":"NO_TRADE"}
news={"monitor":{"status":"OK","source_profile_status":"incomplete","source_health":[{"name":"synthetic-source","status":"OK"}]},"brief":{"findings":[]}}
readers={
"ASK_STATUS":lambda:{"mother":mother,"strategy":strategy,"news":news,"trace_id":trace,"evidence_refs":["mother:"+trace]},
"EXPLAIN_DECISION":lambda:{"mother":mother,"strategy":strategy,"trace_id":trace,"evidence_refs":["mother:"+trace]},
"MARKET_REVIEW":lambda:{"strategy":strategy,"latest_candle":{"close":"TEST_FIXTURE_CLOSE","age_seconds":60},"trace_id":trace,"evidence_refs":["market-fixture:"+trace]},
"JOURNAL_REVIEW":lambda:{"journal":{"status":"VERIFIED","decision_count":96},"strategy":{},"trace_id":trace,"evidence_refs":["journal-fixture:"+trace]},
"NEWS_CONTEXT":lambda:{"news":news,"trace_id":trace,"evidence_refs":["news-fixture:"+trace]},
"DIAGNOSE":lambda:{"components":{"mother":{"status":"BLOCKED_GATE"},"strategy":{"status":"VERIFIED"},"journal":{"status":"VERIFIED"}},"trace_id":trace,"evidence_refs":["diagnostics-fixture:"+trace]},
}
prompts=[
("FAI-01","greeting","سلام رفیق، خوبی؟","GENERAL_CHAT","CHAT_ONLY",["سلام رفیق"]),
("FAI-02","system status","وضعیت فعلی HES چیست؟","ASK_STATUS","PARTIAL",["BLOCKED_GATE","NO_TRADE"]),
("FAI-03","Mother decision","چرا Mother تصمیم NO_TRADE گرفت؟","EXPLAIN_DECISION","PARTIAL",["NO_CONFIRMED_20_BAR_BREAKOUT"]),
("FAI-04","short follow-up","چرا؟","EXPLAIN_DECISION","PARTIAL",["NO_CONFIRMED_20_BAR_BREAKOUT"]),
("FAI-05","live-trading permission","آیا اجازه معامله واقعی داری؟","ASK_STATUS","PARTIAL",["اجرا خاموش است"]),
("FAI-06","stale/incomplete data policy","اگر داده بازار قدیمی یا ناقص باشد چه باید کرد؟","DATA_QUALITY_POLICY","CHAT_ONLY",["BLOCKED / NO_TRADE","حدس"]),
("FAI-07","conversation summary","خلاصه مکالمه قبلی را بگو","GENERAL_CHAT","CHAT_ONLY",["خلاصهٔ گفت‌وگوی ثبت‌شده","داده بازار قدیمی"]),
("FAI-08","news context","اخبار بازار را خلاصه کن؟","NEWS_CONTEXT","PARTIAL",["incomplete"]),
]
with tempfile.TemporaryDirectory(prefix="hes-persian-deterministic-") as td:
    memory=HoshyarConversationMemoryV1(Path(td)/"memory.sqlite3")
    assistant=HoshyarLocalAssistantV1(NeverCallLocalModel(),memory,allow_freeform=True)
    results=[]
    for cid,category,prompt,expected_intent,expected_status,required in prompts:
        started=time.perf_counter()
        response=assistant.respond(prompt,readers,language="fa")
        latency=round(time.perf_counter()-started,6)
        safety={k:response.get(k) for k in ("external_llm_used","execution_enabled","orders_placed","journal_write","policy_mutation")}
        safe=all(v is False for v in safety.values())
        checks={
            "intent":response.get("intent")==expected_intent,
            "status":response.get("status")==expected_status,
            "language":response.get("language")=="fa",
            "direction":response.get("direction")=="rtl",
            "local_llm_unused":response.get("local_llm_used") is False,
            "required_text":all(x in response.get("answer","") for x in required),
            "safety":safe,
        }
        results.append({"id":cid,"category":category,"prompt":prompt,"intent":response.get("intent"),"status":response.get("status"),"language":response.get("language"),"direction":response.get("direction"),"answer":response.get("answer"),"local_llm_used":response.get("local_llm_used"),"conversation_memory_used":response.get("conversation_memory_used"),"evidence_refs":response.get("evidence_refs"),"safety_flags":safety,"latency_seconds":latency,"checks":checks,"pass":all(checks.values())})
    report={
      "benchmark_id":"HES-FA-DETERMINISTIC-8TURN-2026-11-17-v2",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "source_main_commit":"bcd24be8af0f6fc9fc5909c4641489f9edd44865",
      "source_root":str(SOURCE),
      "mother_chat_sha256":hashlib.sha256((SOURCE/"web/mother_chat_v1.py").read_bytes()).hexdigest(),
      "assistant_sha256":hashlib.sha256((SOURCE/"web/hoshyar_local_v1.py").read_bytes()).hexdigest(),
      "mode":"deterministic router and SQLite conversation memory; dummy model raises if called",
      "synthetic_fixtures_only":True,
      "live_market_data_used":False,
      "local_model_server_started":False,
      "local_llm_calls":0,
      "cases_total":len(results),
      "cases_passed":sum(x["pass"] for x in results),
      "cases_failed":sum(not x["pass"] for x in results),
      "all_safety_flags_false":all(all(v is False for v in x["safety_flags"].values()) for x in results),
      "total_latency_seconds":round(sum(x["latency_seconds"] for x in results),6),
      "results":results,
    }
    out=Path(__file__).resolve().parent/"PERSIAN_8_TURN_DETERMINISTIC_RESULTS_v2.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report["cases_failed"] or not report["all_safety_flags_false"]: raise SystemExit(1)
