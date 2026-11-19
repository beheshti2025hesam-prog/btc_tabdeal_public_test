const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("../validation-tools/node_modules/playwright");
const root = path.resolve(__dirname, "..");
const py = fs.readFileSync(path.join(root, "web/dashboard.py"), "utf8");
const html = py.match(/HTML = r'''([\s\S]*?)'''/)[1].replace(/ integrity="[^"]*" crossorigin="anonymous"/, "");
const keys = ["ema_20","ema_50","ema_200","ema_fast_slope_pct","adx_14","plus_di_14","minus_di_14","supertrend_direction","aroon_up_25","aroon_down_25","rsi_14","macd_line","macd_signal","macd_histogram","stochastic_k","stochastic_d","williams_r_14","roc_10_pct","cci_20","atr_14","atr_pct","bollinger_mid","bollinger_upper","bollinger_lower","bollinger_width_pct","bollinger_percent_b","keltner_mid","keltner_upper","keltner_lower","donchian_upper_prior","donchian_lower_prior","vwap_20","relative_volume_20","obv","obv_change_20","mfi_14","cmf_20","choppiness_14","efficiency_ratio_20"];
const regimes = {"4h":"TRANSITION","1h":"RANGE","15m":"BULLISH","1m":"BEARISH"};
const purposes = {BULLISH:"trend continuation and pullback context",BEARISH:"downtrend continuation and rally-fade context",RANGE:"range boundaries and mean-reversion context",TRANSITION:"conflict and regime-transition diagnostics"};
const timeframes = {};
for (const [tf,label] of Object.entries(regimes)) timeframes[tf] = {
 status:"READ_ONLY_RESEARCH",regime:{label,evidence_confidence:.72},candle_count:240,input_sha256:"a".repeat(64),
 indicators:Object.fromEntries(keys.map(k=>[k,{value:1.234,status:"READY",reason:null}])),
 regime_profile:{regime:label,primary_indicators:["ema_20","adx_14"],unavailable_primary_indicators:[],purpose:purposes[label]}
};
const technical={status:"VERIFIED",source:"gateio_public_spot",source_reader:"global_market_data_reader_v1",symbol:"BTC_USDT",canonical_symbol:"BTCUSDT",timeframe_roles:{"4h":"HIGHER_TIMEFRAME_CONTEXT","1h":"HIGHER_TIMEFRAME_CONTEXT","15m":"SETUP_AUTHORITY","1m":"PRECISION_REFINEMENT"},timeframe_roles_status:"INITIAL_BTC_PROFILE",regime_consensus:"MIXED",
 controls:{decision_authority:false,signal_generation_enabled:false,risk_gate_bypass:false,execution_enabled:false,orders_placed:false,journal_write:false,policy_mutation:false},
 timeframes,setup_authority_timeframe:"15m",precision_refinement_timeframe:"1m",failure_codes:[]};
let failTechnical=false;
const chartStub = "window.LightweightCharts={CandlestickSeries:{},LineSeries:{},createChart:function(el){return {addSeries:function(){return {setData:function(){},applyOptions:function(){}}},timeScale:function(){return {fitContent:function(){}}},resize:function(){},applyOptions:function(){}}}};";
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,"http://127.0.0.1");
 const send=(status,body,type="application/json")=>{res.writeHead(status,{"content-type":type,"cache-control":"no-store"});res.end(body);};
 if(u.pathname==="/"){return send(200,html,"text/html; charset=utf-8");}
 if(u.pathname==="/static/dashboard.css"){return send(200,fs.readFileSync(path.join(root,"web/static/dashboard.css")),"text/css");}
 if(u.pathname==="/static/dashboard.js"){return send(200,fs.readFileSync(path.join(root,"web/static/dashboard.js")),"application/javascript");}
 if(u.pathname==="/static/documentation.js"){return send(200,fs.readFileSync(path.join(root,"web/static/documentation.js")),"application/javascript");}
 if(u.pathname==="/static/documentation.css"){return send(200,fs.readFileSync(path.join(root,"web/static/documentation.css")),"text/css");}
 if(u.pathname==="/static/hes-mark.svg"){return send(200,fs.readFileSync(path.join(root,"web/static/hes-mark.svg")),"image/svg+xml");}
 if(u.pathname.includes("lightweight-charts.standalone.production.js")){return send(200,chartStub,"application/javascript");}
 if(u.pathname==="/api/documentation"){
  const language=u.searchParams.get("lang")||"en";
  const catalog=JSON.parse(fs.readFileSync(path.join(root,"docs/documentation/catalog.v1.json"),"utf8"));
  if(!catalog.locales[language])return send(400,JSON.stringify({error:"unsupported_documentation_language"}));
  return send(200,JSON.stringify({schema:"hes.documentation_response.v1",version:catalog.version,updated_at:catalog.updated_at,language,pages:catalog.locales[language],ui:catalog.ui[language],source_register:catalog.source_register,editorial_review:catalog.editorial_review,safety:catalog.safety}));
 }
 if(u.pathname==="/api/technical-intelligence"){const symbol=u.searchParams.get("symbol")||"BTCUSDT",sourceMap={BTCUSDT:"BTC_USDT",ETHUSDT:"ETH_USDT",SOLUSDT:"SOL_USDT"};if(!sourceMap[symbol])return send(400,JSON.stringify({error:"unsupported_symbol"}));if(failTechnical)return send(200,JSON.stringify({status:"BLOCKED",source:"unavailable",source_reader:"unavailable",symbol:sourceMap[symbol],canonical_symbol:symbol,controls:{decision_authority:false,execution_enabled:false,orders_placed:false}}));const btc=symbol==="BTCUSDT";return send(200,JSON.stringify({...technical,symbol:sourceMap[symbol],canonical_symbol:symbol,source_reader:btc?"global_market_data_reader_v1":"native_ohlcv_gateio_v1",timeframe_roles:btc?technical.timeframe_roles:{},timeframe_roles_status:btc?"INITIAL_BTC_PROFILE":"DESCRIPTIVE_ONLY_NOT_YET_VALIDATED_FOR_SYMBOL"}));}
 if(u.pathname==="/api/candles"){
  const interval=u.searchParams.get("interval")||"15m",symbol=u.searchParams.get("symbol")||"BTCUSDT",sourceMap={BTCUSDT:"BTC_USDT",ETHUSDT:"ETH_USDT",SOLUSDT:"SOL_USDT"};
  return send(200,JSON.stringify({status:"ok",source:"gateio_public_spot",source_reader:symbol==="BTCUSDT"?"global_market_data_reader_v1":"native_ohlcv_gateio_v1",venue:"gateio",product:"spot",symbol,source_symbol:sourceMap[symbol],symbol_mapping_verified:!!sourceMap[symbol],execution_instrument_mapping_verified:false,volume_semantics_contract:"gateio_spot_candlestick_volume_v1",trade_count_available:false,taker_buy_flow_available:false,execution_enabled:false,orders_placed:false,interval,gaps:[],latest_age_seconds:8,feature_ready:true,stream_status:"disabled",stream_reason:null,input_batch_sha256:"b".repeat(64),candles:[{open_time:1794927000,close_time:1794927900000,open:"90000",high:"90100",low:"89900",close:"90050",volume:"12"}]}));
 }
 if(u.pathname.startsWith("/api/"))return send(200,JSON.stringify({status:"BLOCKED",error:"fixture_not_configured",decision:"NO_TRADE",market_regime:"UNKNOWN",execution_enabled:false,orders_placed:false,events:[],items:[],sources:[],stages:[],reason_codes:[]}));
 return send(404,"not found","text/plain");
});
(async()=>{
 const browser=await chromium.launch({headless:true});
 const errors=[];let page;
 try{
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const port=server.address().port;
  page=await browser.newPage({viewport:{width:1440,height:1000},locale:"en-US"});
  await page.route("https://**/*",async route=>{
   const url=route.request().url();
   if(url.includes("lightweight-charts.standalone.production.js"))return route.fulfill({status:200,contentType:"application/javascript",body:chartStub});
   return route.fulfill({status:204,body:""});
  });
  page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{if(m.type()==="error")errors.push(m.text())});
  await page.goto("http://127.0.0.1:"+port+"/",{waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>document.querySelector("#technicalStatus")?.textContent==="VERIFIED");
  await page.waitForFunction(()=>document.querySelector("#message")?.textContent.startsWith("VALIDATED"));
  assert.equal(await page.locator("#technicalConsensus").textContent(),"MIXED");
  assert.equal(await page.locator("#technicalSafety").textContent(),"READ ONLY · NO ORDERS");
  assert.equal(await page.locator("#technicalIndicatorRows tr").count(),39);
  await page.selectOption("#technicalTimeframe","4h");
  await page.waitForFunction(()=>document.querySelector("#technicalProfile").textContent.includes("TRANSITION"));
  await page.selectOption("#technicalTimeframe","1m");
  await page.waitForFunction(()=>document.querySelector("#technicalProfile").textContent.includes("BEARISH"));
  await page.selectOption("#symbol","ETHUSDT");
  await page.waitForFunction(()=>document.querySelector("#technicalProvenance").textContent.includes("ETH_USDT")&&document.querySelector("#technicalProvenance").textContent.includes("DESCRIPTIVE_ONLY_NOT_YET_VALIDATED_FOR_SYMBOL"));
  assert.ok((await page.locator("#technicalRegimeMetrics").textContent()).includes("DESCRIPTIVE ONLY"));
  await page.selectOption("#symbol","SOLUSDT");
  await page.waitForFunction(()=>document.querySelector("#technicalProvenance").textContent.includes("SOL_USDT"));
  await page.selectOption("#symbol","BTCUSDT");
  await page.waitForFunction(()=>document.querySelector("#technicalProvenance").textContent.includes("BTC_USDT"));
  await page.selectOption("#languageSelect","fa");
  await page.waitForFunction(()=>document.documentElement.dir==="rtl");
  await page.waitForFunction(()=>document.querySelector("#documentationTitle")?.textContent==="مستندات"&&document.querySelectorAll("#documentationIndex button").length===13&&document.querySelector("#documentationStatus")?.textContent.includes("1.0.4"));
  assert.ok((await page.locator("#documentationArticle").textContent()).includes("DNA"));
  assert.equal(await page.locator("#documentationSafety").textContent(),"فقط‌خواندنی");
  await page.selectOption("#languageSelect","de");
  await page.waitForFunction(()=>document.querySelector("#documentationTitle")?.textContent==="Dokumentation"&&document.querySelector("#documentationArticle .documentation-article-title")?.textContent==="Projekt-DNA und Produktidentität");
  assert.equal(await page.evaluate(()=>document.documentElement.dir),"ltr");
  await page.selectOption("#languageSelect","fr");
  await page.waitForFunction(()=>document.querySelector("#documentationTitle")?.textContent==="Documentation"&&document.querySelector("#documentationArticle .documentation-article-title")?.textContent==="ADN du projet et identité du produit");
  assert.equal(await page.evaluate(()=>document.documentElement.dir),"ltr");
  await page.selectOption("#languageSelect","fa");
  await page.waitForFunction(()=>document.querySelector("#documentationTitle")?.textContent==="مستندات"&&document.documentElement.dir==="rtl");
  assert.ok((await page.locator("#technicalIntelligenceTitle").textContent()).includes("هوش فنی"));
  assert.ok((await page.locator("#technicalIndicatorRows").textContent()).includes("روند"));
  assert.ok((await page.locator("#technicalIntelligencePanel").textContent()).includes("پژوهش فقط‌خواندنی"));
  assert.ok((await page.locator("body").textContent()).includes("نمودار بازار و اندیکاتورها"));
  const rtl=await page.evaluate(()=>({dir:document.documentElement.dir,bodyDirection:getComputedStyle(document.body).direction,scrollWidth:document.documentElement.scrollWidth,innerWidth:innerWidth}));
  assert.equal(rtl.dir,"rtl");assert.equal(rtl.bodyDirection,"rtl");
  fs.mkdirSync(path.join(root,"artifacts"),{recursive:true});
  await page.screenshot({path:path.join(root,"artifacts/universal-indicator-dashboard-desktop-rtl.png"),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(150);
  const mobile=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:innerWidth,panelWidth:document.querySelector("#technicalIntelligencePanel").getBoundingClientRect().width}));
  assert.ok(mobile.scrollWidth<=mobile.innerWidth+1,JSON.stringify(mobile));
  assert.ok(mobile.panelWidth<=mobile.innerWidth,JSON.stringify(mobile));
  await page.screenshot({path:path.join(root,"artifacts/universal-indicator-dashboard-mobile-rtl.png"),fullPage:true});
  failTechnical=true;await page.click("#technicalRefresh");
  await page.waitForFunction(()=>document.querySelector("#technicalStatus")?.textContent==="BLOCKED");
  assert.ok((await page.locator("#technicalProvenance").textContent()).includes("FAIL CLOSED"));
  assert.deepEqual(errors,[]);
  const result={status:"PASS",desktop:"1440x1000",mobile:"390x844",rtl,mobile_layout:mobile,
   indicator_rows:39,timeframe_switches:["15m","4h","1m"],symbol_switches:["BTCUSDT","ETHUSDT","SOLUSDT"],fail_closed:true,read_only:true,orders_placed:false,
   browser_errors:errors,screenshots:["artifacts/universal-indicator-dashboard-desktop-rtl.png","artifacts/universal-indicator-dashboard-mobile-rtl.png"]};
  fs.writeFileSync(path.join(root,"artifacts/universal-indicator-dashboard-browser-report.json"),JSON.stringify(result,null,2)+"\n");
  console.log(JSON.stringify(result,null,2));
 }finally{
  if(page)await page.close().catch(()=>{});
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
