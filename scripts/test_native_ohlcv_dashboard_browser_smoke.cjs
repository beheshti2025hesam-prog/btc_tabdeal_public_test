const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, locale: "en-US" });
    let candlePayload = null;
    let signalPayload = null;
    let externalChartCdnRequested = false;
    let directMarketDataRequest = false;
    let chartAssetResponse = null;
    const consoleErrors = [];
    const pageErrors = [];
    const requestFailures = [];
    page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", error => pageErrors.push(String(error.stack || error)));
    page.on("requestfailed", request => requestFailures.push({ url: request.url(), failure: request.failure()?.errorText || "unknown" }));

    page.on("request", request => {
      const url = request.url();
      if (url.startsWith("https://unpkg.com/") || url.startsWith("https://cdn.jsdelivr.net/")) {
        externalChartCdnRequested = true;
      }
      if (url.startsWith("https://api.gateio.ws/") || url.startsWith("https://api.binance.com/") ||
          url.startsWith("https://data-api.binance.vision/")) {
        directMarketDataRequest = true;
      }
    });
    page.on("response", async response => {
      try {
        const responseUrl = new URL(response.url());
        if (responseUrl.pathname === "/static/third_party/lightweight-charts/5.0.8/lightweight-charts.standalone.production.js") {
          chartAssetResponse = { status: response.status(), content_type: response.headers()["content-type"] || null };
        }
        const url = new URL(response.url());
        if (url.pathname === "/api/candles" && response.status() === 200) {
          const body = await response.json();
          if (Array.isArray(body.candles) && body.candles.length) candlePayload = body;
        }
        if (url.pathname === "/api/signal" && response.status() === 200) {
          signalPayload = await response.json();
        }
      } catch (_) {}
    });

    await page.goto("http://127.0.0.1:8765/", { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForFunction(
      () => document.querySelector("#message")?.textContent?.startsWith("VALIDATED"),
      null,
      { timeout: 90000 }
    );
    await page.waitForFunction(() => {
      const canvas = document.querySelector("#chart canvas");
      return !!canvas && canvas.getBoundingClientRect().width > 100 && canvas.getBoundingClientRect().height > 100;
    }, null, { timeout: 15000 });

    await page.waitForFunction(
      () => document.querySelector("#signalStatus")?.textContent && document.querySelector("#signalStatus").textContent !== "Checking gates…",
      null,
      { timeout: 15000 }
    );
    assert.ok(candlePayload, "successful /api/candles payload was not observed");
    assert.ok(signalPayload, "successful /api/signal payload was not observed");
    assert.ok(candlePayload.candles.length > 0, "source returned no candles");
    assert.equal(signalPayload.source, candlePayload.source, "signal and chart source identities differ");
    assert.equal(signalPayload.source_reader, candlePayload.source_reader, "signal and chart reader identities differ");
    assert.equal(signalPayload.input_batch_sha256, candlePayload.input_batch_sha256, "signal and chart input batches differ");
    assert.equal(signalPayload.decision, "NO_TRADE", "unapproved signal path must fail closed");
    assert.equal(signalPayload.status, "BLOCKED", "missing risk/structure providers must block signal");
    assert.equal(signalPayload.execution_enabled, false, "signal route must never enable execution");
    assert.equal(candlePayload.source, "gateio_public_spot");
    assert.equal(candlePayload.source_reader, "global_market_data_reader_v1");
    assert.equal(candlePayload.source_symbol, "BTC_USDT");
    assert.equal(candlePayload.symbol_mapping_verified, true);
    assert.equal(candlePayload.volume_semantics_contract, "gateio_spot_candlestick_volume_v1");
    assert.equal(candlePayload.trade_count_available, false);
    assert.equal(candlePayload.taker_buy_flow_available, false);
    assert.equal(candlePayload.venue, "gateio");
    assert.equal(candlePayload.execution_enabled, false);
    assert.equal(externalChartCdnRequested, false, "chart must not request a remote CDN");
    assert.equal(directMarketDataRequest, false, "dashboard must read the persisted global feed, not call an exchange REST endpoint");

    const last = candlePayload.candles[candlePayload.candles.length - 1];
    const ui = await page.evaluate(() => ({
      price: document.querySelector("#price").textContent,
      stamp: document.querySelector("#stamp").textContent,
      volume: document.querySelector("#volume").textContent,
      count: document.querySelector("#count").textContent,
      message: document.querySelector("#message").textContent,
      canvas: (() => {
        const c = document.querySelector("#chart canvas");
        const r = c.getBoundingClientRect();
        return { width: r.width, height: r.height };
      })(),
      chartLibraryLoaded: typeof LightweightCharts !== "undefined",
      chartSeriesExists: typeof candleSeries !== "undefined" && !!candleSeries,
      chartScriptIntegrity: document.querySelector('script[src*="lightweight-charts.standalone.production.js"]')?.integrity || null,
      bars: typeof bars !== "undefined" ? bars.map(b => ({
        open_time: b.open_time, open: Number(b.open), high: Number(b.high), low: Number(b.low),
        close: Number(b.close), volume: String(b.volume)
      })) : null
    }));

    assert.equal(Number(ui.price.replaceAll(",", "")), Number(last.close), "displayed close differs from latest source candle");
    assert.equal(ui.volume, last.volume, "displayed volume differs from latest source candle");
    assert.equal(ui.count, String(candlePayload.candles.length), "displayed candle count differs from source batch");
    const candlePixels = await page.evaluate(() => {
      const canvases = [...document.querySelectorAll("#chart canvas")];
      let green = 0;
      let red = 0;
      let sampled = 0;
      for (const canvas of canvases) {
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx || canvas.width === 0 || canvas.height === 0) continue;
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        // Sample every fourth pixel; chart candles use these configured up/down colors.
        for (let p = 0; p < pixels.length; p += 16) {
          const r = pixels[p], g = pixels[p + 1], b = pixels[p + 2], a = pixels[p + 3];
          if (a < 160) continue;
          sampled++;
          if (Math.abs(r - 54) < 35 && Math.abs(g - 201) < 45 && Math.abs(b - 143) < 45) green++;
          if (Math.abs(r - 241) < 35 && Math.abs(g - 107) < 45 && Math.abs(b - 117) < 45) red++;
        }
      }
      return { canvas_count: canvases.length, sampled_pixels: sampled, green_candle_color_pixels: green, red_candle_color_pixels: red };
    });
    assert.ok(candlePixels.canvas_count > 0, "no chart canvas was rendered");
    const visibleCandlePixelCount = candlePixels.green_candle_color_pixels + candlePixels.red_candle_color_pixels;
    // Preserve diagnostics even when the visual assertion fails, so the CI artifact can show the failure.
    await page.screenshot({ path: "artifacts/native-ohlcv-dashboard-browser-smoke.png", fullPage: true });
    const diagnosticEvidence = {
      schema_version: 1,
      status: visibleCandlePixelCount >= 8 ? "PASS" : "FAIL_VISIBLE_CANDLES",
      source: candlePayload.source,
      source_reader: candlePayload.source_reader,
      source_symbol: candlePayload.source_symbol,
      symbol_mapping_verified: candlePayload.symbol_mapping_verified,
      volume_semantics_contract: candlePayload.volume_semantics_contract,
      trade_count_available: candlePayload.trade_count_available,
      taker_buy_flow_available: candlePayload.taker_buy_flow_available,
      venue: candlePayload.venue,
      symbol: candlePayload.symbol,
      source_symbol: candlePayload.source_symbol,
      symbol_mapping_verified: candlePayload.symbol_mapping_verified,
      interval: candlePayload.interval,
      input_batch_sha256: candlePayload.input_batch_sha256,
      signal_input_batch_sha256: signalPayload.input_batch_sha256,
      signal_source_reader: signalPayload.source_reader,
      signal_status: signalPayload.status,
      signal_decision: signalPayload.decision,
      signal_same_batch_provenance: signalPayload.input_batch_sha256 === candlePayload.input_batch_sha256,
      candle_count: candlePayload.candles.length,
      chart_canvas: ui.canvas,
      chart_library_loaded: ui.chartLibraryLoaded,
      chart_series_exists: ui.chartSeriesExists,
      chart_script_integrity: ui.chartScriptIntegrity,
      chart_asset_response: chartAssetResponse,
      visible_candle_pixels: candlePixels,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      request_failures: requestFailures,
      message: ui.message,
      execution_enabled: false
    };
    require("node:fs").writeFileSync("artifacts/native-ohlcv-dashboard-browser-smoke.json", JSON.stringify(diagnosticEvidence, null, 2) + "\n");
    assert.ok(
      visibleCandlePixelCount >= 8,
      `candlestick series is not visibly rendered: ${JSON.stringify({ ...candlePixels, chartAssetResponse, chartLibraryLoaded: ui.chartLibraryLoaded, chartSeriesExists: ui.chartSeriesExists, consoleErrors, pageErrors })}`
    );

    assert.ok(ui.bars, "browser could not inspect the dashboard's candle batch");
    assert.equal(ui.bars.length, candlePayload.candles.length, "chart input batch length differs from API batch");
    for (let i = 0; i < candlePayload.candles.length; i++) {
      const source = candlePayload.candles[i];
      const chart = ui.bars[i];
      assert.equal(chart.open_time, source.open_time, `chart open_time differs at candle ${i}`);
      for (const field of ["open", "high", "low", "close"]) {
        assert.equal(chart[field], Number(source[field]), `chart ${field} differs at candle ${i}`);
      }
      assert.equal(chart.volume, source.volume, `chart volume differs at candle ${i}`);
    }

    const stamp = new Date(last.close_time).toISOString().replace("T", " ").replace(".000Z", " UTC");
    assert.equal(ui.stamp, stamp, "displayed UTC candle time differs from source batch");

    const responsiveViewports = [];
    for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1440, height: 1000 }]) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(150);
      const layout = await page.evaluate(() => {
        const canvas = document.querySelector("#chart canvas");
        const rect = canvas?.getBoundingClientRect();
        return {
          viewportWidth: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          chartWidth: rect ? rect.width : 0,
          chartHeight: rect ? rect.height : 0,
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1
        };
      });
      assert.ok(layout.chartWidth > 200 && layout.chartHeight > 200, "chart is not usable at viewport " + viewport.width + ": " + JSON.stringify(layout));
      assert.equal(layout.horizontalOverflow, false, "horizontal overflow at viewport " + viewport.width + ": " + JSON.stringify(layout));
      responsiveViewports.push(layout);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });

    await page.screenshot({ path: "artifacts/native-ohlcv-dashboard-browser-smoke.png", fullPage: true });
    const evidence = {
      schema_version: 1,
      status: "PASS",
      source: candlePayload.source,
      source_reader: candlePayload.source_reader,
      source_symbol: candlePayload.source_symbol,
      symbol_mapping_verified: candlePayload.symbol_mapping_verified,
      volume_semantics_contract: candlePayload.volume_semantics_contract,
      trade_count_available: candlePayload.trade_count_available,
      taker_buy_flow_available: candlePayload.taker_buy_flow_available,
      venue: candlePayload.venue,
      product: candlePayload.product,
      symbol: candlePayload.symbol,
      interval: candlePayload.interval,
      input_batch_sha256: candlePayload.input_batch_sha256,
      signal_input_batch_sha256: signalPayload.input_batch_sha256,
      signal_source_reader: signalPayload.source_reader,
      signal_status: signalPayload.status,
      signal_decision: signalPayload.decision,
      signal_same_batch_provenance: signalPayload.input_batch_sha256 === candlePayload.input_batch_sha256,
      candle_count: candlePayload.candles.length,
      chart_canvas: ui.canvas,
      responsive_viewports: responsiveViewports,
      visible_candle_pixels: candlePixels,
      external_chart_cdn_requested: externalChartCdnRequested,
      direct_market_data_request_from_browser: directMarketDataRequest,
      displayed_close_matches_source: true,
      displayed_volume_matches_source: true,
      chart_input_batch_matches_api_batch: true,
      chart_all_candles_match_api_batch: true,
      execution_enabled: false,
      message: ui.message
    };
    require("node:fs").writeFileSync("artifacts/native-ohlcv-dashboard-browser-smoke.json", JSON.stringify(evidence, null, 2) + "\n");
    process.stdout.write(JSON.stringify(evidence) + "\n");
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(String(error.stack || error) + "\n");
  process.exit(1);
});
