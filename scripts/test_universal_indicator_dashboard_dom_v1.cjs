const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("../validation-tools/node_modules/jsdom");
const root = path.resolve(__dirname, "..");
const py = fs.readFileSync(path.join(root, "web/dashboard.py"), "utf8");
const match = py.match(/HTML = r'''([\s\S]*?)'''/);
assert.ok(match, "dashboard HTML template must exist");
const dom = new JSDOM(match[1], { url: "http://127.0.0.1:18766/", runScripts: "outside-only" });
const { window } = dom;
window.setInterval = () => 0;
const indicatorKeys = ["ema_20","ema_50","ema_200","ema_fast_slope_pct","adx_14","plus_di_14","minus_di_14","supertrend_direction","aroon_up_25","aroon_down_25","rsi_14","macd_line","macd_signal","macd_histogram","stochastic_k","stochastic_d","williams_r_14","roc_10_pct","cci_20","atr_14","atr_pct","bollinger_mid","bollinger_upper","bollinger_lower","bollinger_width_pct","bollinger_percent_b","keltner_mid","keltner_upper","keltner_lower","donchian_upper_prior","donchian_lower_prior","vwap_20","relative_volume_20","obv","obv_change_20","mfi_14","cmf_20","choppiness_14","efficiency_ratio_20"];
const labels = {"4h":"TRANSITION","1h":"RANGE","15m":"BULLISH","1m":"BEARISH"};
const purpose = {BULLISH:"trend continuation and pullback context",BEARISH:"downtrend continuation and rally-fade context",RANGE:"range boundaries and mean-reversion context",TRANSITION:"conflict and regime-transition diagnostics"};
const timeframes = {};
for (const [tf,label] of Object.entries(labels)) timeframes[tf] = {
 status:"READ_ONLY_RESEARCH",regime:{label,evidence_confidence:0.72},candle_count:240,
 input_sha256:"a".repeat(64),indicators:Object.fromEntries(indicatorKeys.map(k=>[k,{value:1.234,status:"READY",reason:null}])),
 regime_profile:{regime:label,primary_indicators:label==="RANGE"?["rsi_14","bollinger_upper"]:["ema_20","adx_14"],unavailable_primary_indicators:[],purpose:purpose[label]}
};
const technicalPayload={status:"VERIFIED",source:"gateio_public_spot",source_reader:"global_market_data_reader_v1",symbol:"BTC_USDT",canonical_symbol:"BTCUSDT",timeframe_roles:{"4h":"HIGHER_TIMEFRAME_CONTEXT","1h":"HIGHER_TIMEFRAME_CONTEXT","15m":"SETUP_AUTHORITY","1m":"PRECISION_REFINEMENT"},timeframe_roles_status:"INITIAL_BTC_PROFILE",regime_consensus:"MIXED",
 controls:{execution_enabled:false,orders_placed:false,decision_authority:false},timeframes,failure_codes:[]};
let failTechnical=false;
window.fetch = async (url, options) => String(url).startsWith("/api/technical-intelligence")
 ? (failTechnical ? new Response("{}",{status:503,headers:{"content-type":"application/json"}}) : new Response(JSON.stringify(technicalPayload),{status:200,headers:{"content-type":"application/json"}}))
 : new Response("{}", {status:503, headers:{"content-type":"application/json"}});
const errors = [];
window.console.error = (...args) => errors.push(args.join(" "));
window.eval(fs.readFileSync(path.join(root, "web/static/dashboard.js"), "utf8"));
async function waitFor(fn, ms=12000) {
 const start=Date.now();
 while(Date.now()-start<ms) { if(fn()) return; await new Promise(r=>setTimeout(r,40)); }
 throw new Error("DOM readiness timeout");
}
(async()=>{
 try {
  await waitFor(()=>window.document.querySelector("#technicalStatus")?.textContent==="VERIFIED");
  const d=window.document;
  assert.ok(d.querySelector("#technicalIntelligencePanel"));
  assert.equal(d.querySelector("#technicalSafety").textContent,"READ ONLY · NO ORDERS");
  assert.equal(d.querySelector("#technicalConsensus").textContent,"MIXED");
  assert.ok(d.querySelectorAll("#technicalRegimeMetrics .metric").length===4);
  assert.ok(d.querySelectorAll("#technicalIndicatorRows tr").length>=30);
  assert.ok(d.querySelector("#technicalIndicatorRows").textContent.includes("adx_14"));
  assert.ok(d.querySelector("#technicalProfile").textContent.includes("BULLISH"));
  const tf=d.querySelector("#technicalTimeframe");
  tf.value="4h";tf.dispatchEvent(new window.Event("change",{bubbles:true}));
  assert.ok(d.querySelector("#technicalProfile").textContent.includes("TRANSITION"));
  assert.ok(d.querySelector("#technicalIndicatorRows").textContent.includes("ema_20"));
  tf.value="1m";tf.dispatchEvent(new window.Event("change",{bubbles:true}));
  await new Promise(r=>setTimeout(r,100));
  assert.ok(d.querySelector("#technicalProfile").textContent.includes("Regime-adaptive research profile"), "1m profile not rendered: "+d.querySelector("#technicalProfile").textContent);
  assert.ok(d.querySelector("#technicalProfile").textContent.includes("BEARISH"));
  const language=d.querySelector("#languageSelect");language.value="fa";language.dispatchEvent(new window.Event("change",{bubbles:true}));
  assert.equal(d.documentElement.dir,"rtl");
  assert.ok(d.querySelector("#technicalIntelligenceTitle").textContent.includes("هوش فنی"));
  assert.ok(d.querySelector("#technicalProfile").textContent.includes("اصلی:"));
  assert.ok(d.querySelector("#technicalIndicatorRows").textContent.includes("روند"));
  assert.ok(d.querySelector("#technicalIntelligencePanel").textContent.includes("پژوهش فقط‌خواندنی"));
  assert.ok(d.body.textContent.includes("نمودار بازار و اندیکاتورها"));
  assert.ok(d.querySelector("#technicalRegimeMetrics").textContent.includes("مرجع ستاپ"));
  const verifiedStatus=d.querySelector("#technicalStatus").textContent;
  const verifiedIndicatorRows=d.querySelectorAll("#technicalIndicatorRows tr").length;
  failTechnical=true;d.querySelector("#technicalRefresh").click();
  await waitFor(()=>d.querySelector("#technicalStatus")?.textContent==="BLOCKED");
  assert.ok(d.querySelector("#technicalProvenance").textContent.includes("FAIL CLOSED"));
  const css=fs.readFileSync(path.join(root,"web/static/dashboard.css"),"utf8");
  assert.ok(/@media[^{]*(max-width|orientation)/i.test(css),"responsive CSS breakpoint must exist");
  assert.ok(/direction\s*:\s*rtl/i.test(css) || /:lang\(fa\)/i.test(css),"RTL language styling must exist");
  console.log(JSON.stringify({status:"PASS",technical_status_verified:verifiedStatus,technical_status_after_failure:d.querySelector("#technicalStatus").textContent,
   consensus:"MIXED",indicator_rows_verified:verifiedIndicatorRows,
   timeframe_switches:["15m","4h","1m"],safety:d.querySelector("#technicalSafety").textContent,
   responsive_css:true,rtl_css:true,fail_closed_test:true,console_errors:errors},null,2));
  await new Promise(r=>setTimeout(r,250));
 } finally { /* MutationObserver is drained by the process event loop. */ }
})().catch(e=>{console.error(e);process.exitCode=1;});
