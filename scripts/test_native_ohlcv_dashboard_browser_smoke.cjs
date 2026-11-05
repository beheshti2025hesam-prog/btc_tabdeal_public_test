const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const dashboardBaseUrl = process.env.HES_DASHBOARD_SMOKE_BASE_URL || "http://127.0.0.1:8765";

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, locale: "en-US" });
    let candlePayload = null;
    const candlePayloads = {};
    let strategyV2Payload = null;
    let strategyV2StatusCode = null;
    const apiContractResponses = {};
    let externalChartCdnRequested = false;
    let directMarketDataRequest = false;
    let chartAssetResponse = null;
    let logoAssetResponse = null;
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
        if (responseUrl.pathname === "/static/hes-mark.svg") {
          logoAssetResponse = { status: response.status(), content_type: response.headers()["content-type"] || null };
        }
        const url = new URL(response.url());
        if (url.pathname.startsWith("/api/")) {
          const body = await response.json();
          apiContractResponses[url.pathname] = {
            status: response.status(),
            schema: body.schema || body.schema_version || null
          };
          if (url.pathname === "/api/candles" && response.status() === 200 &&
              Array.isArray(body.candles) && body.candles.length) {
            candlePayload = body;
            candlePayloads[body.interval] = body;
          }
          if (url.pathname === "/api/strategy-v2" && [200, 503].includes(response.status())) {
            strategyV2StatusCode = response.status();
            strategyV2Payload = body;
          }
        }
      } catch (_) {}
    });

    await page.goto(dashboardBaseUrl + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
    try {
      await page.waitForFunction(() => {
        const message = document.querySelector("#message")?.textContent || "";
        return message.startsWith("VALIDATED") || message.startsWith("FAIL CLOSED");
      }, null, { timeout: 30000 });
    } catch (error) {
      const diagnostics = await Promise.race([
        page.evaluate(() => ({
          message: document.querySelector("#message")?.textContent || null,
          chartLibraryLoaded: typeof LightweightCharts !== "undefined",
          chartElement: !!document.querySelector("#chart"),
          scriptStates: [...document.scripts].map(script => ({
            src: script.src || "inline",
            loaded: !script.src || script.dataset.loaded === "true"
          }))
        })),
        new Promise(resolve => setTimeout(() => resolve({ page_unresponsive: true }), 5000))
      ]);
      await page.screenshot({
        path: "artifacts/native-ohlcv-dashboard-browser-smoke.png",
        fullPage: true,
        timeout: 5000
      }).catch(error => { diagnostics.screenshotError = String(error); });
      require("node:fs").writeFileSync(
        "artifacts/native-ohlcv-dashboard-browser-smoke.json",
        JSON.stringify({ schema_version: 1, status: "FAIL_READINESS_TIMEOUT", diagnostics, consoleErrors, pageErrors, requestFailures, candlePayloadObserved: !!candlePayload, strategyV2StatusCode, chartAssetResponse }, null, 2) + "\n"
      );
      throw new Error("dashboard readiness timeout: " + JSON.stringify({ diagnostics, consoleErrors, pageErrors, requestFailures, candlePayloadObserved: !!candlePayload, strategyV2StatusCode, chartAssetResponse, cause: String(error) }));
    }
    const readinessMessage = await page.locator("#message").textContent();
    assert.ok(readinessMessage.startsWith("VALIDATED"), "dashboard failed closed before chart acceptance: " + JSON.stringify({ readinessMessage, consoleErrors, pageErrors, requestFailures, candlePayloadObserved: !!candlePayload, strategyV2StatusCode, chartAssetResponse }));
    await page.waitForFunction(() => {
      const canvas = document.querySelector("#chart canvas");
      return !!canvas && canvas.getBoundingClientRect().width > 100 && canvas.getBoundingClientRect().height > 100;
    }, null, { timeout: 15000 });

    await page.waitForFunction(
      () => document.querySelector("#v2Status")?.textContent && document.querySelector("#v2Status").textContent !== "Checking report…",
      null,
      { timeout: 15000 }
    );
    await page.waitForFunction(
      () => {
        const ids = ["journalStatus", "motherReasons", "newsSummary", "peReasons"];
        return ids.every(id => {
          const value = document.querySelector("#" + id)?.textContent || "";
          return value && !/^(Loading|Verifying|Waiting)/.test(value);
        });
      },
      null,
      { timeout: 30000 }
    );
    const fifteenMinutePayload = candlePayload;
    assert.ok(fifteenMinutePayload, "successful /api/candles payload was not observed");
    assert.equal(fifteenMinutePayload.interval, "15m", "15m must remain the default chart interval");
    assert.equal(await page.locator("#interval").inputValue(), "15m");
    assert.ok(candlePayloads["15m"], "15m API batch was not retained");
    assert.ok(strategyV2Payload, "canonical Strategy V2 response was not observed");
    assert.equal(candlePayload.schema, "hes.market_candles_view.v1");
    assert.equal(strategyV2Payload.schema, "hes.strategy_v2_dashboard_view.v1");
    assert.equal(apiContractResponses["/api/journal"]?.schema, "hes.trade_journal_view.v1",
      "decision journal API schema must be versioned");
    assert.equal(apiContractResponses["/api/mother"]?.schema, "hes.mother_v2_dashboard_view.v1",
      "Mother API schema must be versioned even when blocked");
    assert.equal(apiContractResponses["/api/precision-entry"]?.schema, "hes_precision_entry_status_v1",
      "Precision Entry API schema must be versioned even when blocked");
    assert.ok(["hes.news_monitor_snapshot.v1", "hes.api_error.v1"].includes(apiContractResponses["/api/news"]?.schema),
      "News API must return a versioned success or error contract");
    assert.ok(candlePayload.candles.length > 0, "source returned no candles");
    assert.equal(strategyV2Payload.decision, "NO_TRADE", "paper-only V2 dashboard must remain NO_TRADE");
    assert.equal(strategyV2Payload.execution_enabled, false, "V2 dashboard must never enable execution");
    assert.equal(strategyV2Payload.orders_placed, false, "V2 dashboard must never place orders");
    if (strategyV2StatusCode === 503) {
      assert.equal(strategyV2Payload.status, "BLOCKED", "missing V2 report/journal must fail closed");
      assert.equal(strategyV2Payload.fail_closed, true, "missing V2 evidence must be explicitly fail-closed");
    } else {
      assert.equal(strategyV2Payload.status, "VERIFIED", "available V2 evidence must validate");
      assert.equal(strategyV2Payload.source, "gateio_public_spot");
      assert.equal(strategyV2Payload.symbol, "BTC_USDT");
    }
    assert.equal(candlePayload.source, "gateio_public_spot");
    assert.equal(candlePayload.status, "ok", "chart must only accept a gap-free market-data batch");
    assert.deepEqual(candlePayload.gaps, [], "chart must only accept a gap-free market-data batch");
    assert.equal(candlePayload.source_reader, "global_market_data_reader_v1");
    assert.equal(candlePayload.source_symbol, "BTC_USDT");
    assert.equal(candlePayload.symbol_mapping_verified, true);
    assert.equal(candlePayload.execution_instrument_mapping_verified, false);
    assert.equal(candlePayload.volume_semantics_contract, "gateio_spot_candlestick_volume_v1");
    assert.equal(candlePayload.trade_count_available, false);
    assert.equal(candlePayload.taker_buy_flow_available, false);
    assert.equal(candlePayload.venue, "gateio");
    assert.equal(candlePayload.execution_enabled, false);
    assert.equal(logoAssetResponse?.status, 200, "HES logo asset must be served locally");
    assert.ok((logoAssetResponse?.content_type || "").startsWith("image/svg+xml"), "HES logo must be served as SVG");
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
      logo: (() => { const img = document.querySelector(".brand-mark"); return img ? { complete: img.complete, naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight, src: img.getAttribute("src") } : null; })(),
      bars: typeof bars !== "undefined" ? bars.map(b => ({
        open_time: b.open_time, open: Number(b.open), high: Number(b.high), low: Number(b.low),
        close: Number(b.close), volume: String(b.volume)
      })) : null
    }));

    assert.ok(ui.logo && ui.logo.complete && ui.logo.naturalWidth > 0 && ui.logo.naturalHeight > 0, "HES logo image did not render");

    const languageSelect = page.locator("#languageSelect");
    const motherTitle = page.locator("#motherTitle");
    const decisionHeader = page.locator("#journalPanel thead th").nth(2);
    assert.equal((await motherTitle.textContent()).trim(), "Mother Orchestrator · canonical V2 evidence chain",
      "English canonical Mother heading was altered");
    assert.equal((await decisionHeader.textContent()).trim(), "Decision");
    await languageSelect.selectOption("de");
    await page.waitForFunction(() => document.documentElement.lang === "de" &&
      document.querySelector("#motherTitle")?.textContent.includes("kanonische V2-Nachweiskette"));
    assert.equal(await page.locator('.section-nav a[href="#motherPanel"]').textContent(), "Orchestrator");
    assert.equal((await decisionHeader.textContent()).trim(), "Entscheidung");
    assert.equal(await page.evaluate(() => localStorage.getItem("hes-dashboard-locale-v1")), "de");
    await languageSelect.selectOption("fa");
    await page.waitForFunction(() => document.documentElement.lang === "fa" && document.documentElement.dir === "rtl");
    assert.equal((await decisionHeader.textContent()).trim(), "تصمیم");
    assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector("#chart")).direction), "ltr",
      "chart canvas must remain LTR under Persian UI");
    await languageSelect.selectOption("fr");
    await page.waitForFunction(() => document.documentElement.lang === "fr" && document.documentElement.dir === "ltr");
    assert.equal((await decisionHeader.textContent()).trim(), "Décision");
    await languageSelect.selectOption("en");
    await page.waitForFunction(() => document.documentElement.lang === "en" &&
      document.querySelector("#motherTitle")?.textContent.trim() === "Mother Orchestrator · canonical V2 evidence chain");
    assert.equal(await page.locator('.section-nav a[href="#motherPanel"]').textContent(), "Mother",
      "English Mother navigation label was not restored");
    assert.equal((await decisionHeader.textContent()).trim(), "Decision",
      "English Decision label was not restored after ambiguous translations");
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
      execution_instrument_mapping_verified: candlePayload.execution_instrument_mapping_verified,
      volume_semantics_contract: candlePayload.volume_semantics_contract,
      trade_count_available: candlePayload.trade_count_available,
      taker_buy_flow_available: candlePayload.taker_buy_flow_available,
      venue: candlePayload.venue,
      symbol: candlePayload.symbol,
      source_symbol: candlePayload.source_symbol,
      symbol_mapping_verified: candlePayload.symbol_mapping_verified,
      interval: candlePayload.interval,
      input_batch_sha256: candlePayload.input_batch_sha256,
      strategy_v2_status_code: strategyV2StatusCode,
      strategy_v2_status: strategyV2Payload.status,
      strategy_v2_decision: strategyV2Payload.decision,
      strategy_v2_source: strategyV2Payload.source || "gateio_public_spot",
      strategy_v2_symbol: strategyV2Payload.symbol || "BTC_USDT",
      strategy_v2_execution_enabled: strategyV2Payload.execution_enabled,
      api_contract_responses: apiContractResponses,
      candle_count: candlePayload.candles.length,
      chart_canvas: ui.canvas,
      chart_library_loaded: ui.chartLibraryLoaded,
      chart_series_exists: ui.chartSeriesExists,
      chart_script_integrity: ui.chartScriptIntegrity,
      chart_asset_response: chartAssetResponse,
      logo_asset_response: logoAssetResponse,
      logo_rendered: !!ui.logo && ui.logo.complete && ui.logo.naturalWidth > 0 && ui.logo.naturalHeight > 0,
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
      const minimumChartWidth = viewport.width <= 600 ? 200 : viewport.width <= 800 ? 550 : 900;
      await page.waitForFunction((minimum) => {
        const container = document.querySelector("#chart");
        const canvas = document.querySelector("#chart canvas");
        const rect = canvas?.getBoundingClientRect();
        return !!rect && rect.width > minimum && rect.width <= container.clientWidth + 1 &&
          document.documentElement.scrollWidth <= window.innerWidth + 1;
      }, minimumChartWidth, { timeout: 10000 });
      const layout = await page.evaluate(() => {
        const container = document.querySelector("#chart");
        const canvas = document.querySelector("#chart canvas");
        const rect = canvas?.getBoundingClientRect();
        return {
          viewportWidth: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          containerWidth: container.clientWidth,
          chartWidth: rect ? rect.width : 0,
          chartHeight: rect ? rect.height : 0,
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1
        };
      });
      assert.ok(layout.chartWidth > minimumChartWidth && layout.chartHeight > 200, "chart is not usable at viewport " + viewport.width + ": " + JSON.stringify(layout));
      assert.ok(layout.chartWidth <= layout.containerWidth + 1, "chart canvas did not resize to its container at viewport " + viewport.width + ": " + JSON.stringify(layout));
      assert.equal(layout.horizontalOverflow, false, "horizontal overflow at viewport " + viewport.width + ": " + JSON.stringify(layout));
      responsiveViewports.push(layout);
    }

    const oneMinuteResponsePromise = page.waitForResponse(response => {
      try {
        const url = new URL(response.url());
        return url.pathname === "/api/candles" && url.searchParams.get("interval") === "1m" && response.status() === 200;
      } catch (_) { return false; }
    });
    await page.locator("#interval").selectOption("1m");
    const oneMinuteResponse = await oneMinuteResponsePromise;
    const oneMinutePayload = await oneMinuteResponse.json();
    candlePayloads["1m"] = oneMinutePayload;
    assert.equal(oneMinutePayload.interval, "1m");
    await page.waitForFunction(
      count => document.querySelector("#count")?.textContent === String(count) &&
        document.querySelector("#message")?.textContent?.startsWith("VALIDATED"),
      oneMinutePayload.candles.length,
      { timeout: 15000 }
    );
    candlePayload = oneMinutePayload;
    assert.ok(candlePayloads["1m"], "1m API batch was not retained");
    const oneMinuteUi = await page.evaluate(() => ({
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
      bars: typeof bars !== "undefined" ? bars.map(b => ({
        open_time: b.open_time, open: Number(b.open), high: Number(b.high), low: Number(b.low),
        close: Number(b.close), volume: String(b.volume)
      })) : null
    }));
    const oneMinuteLast = oneMinutePayload.candles[oneMinutePayload.candles.length - 1];
    assert.equal(Number(oneMinuteUi.price.replaceAll(",", "")), Number(oneMinuteLast.close));
    assert.equal(oneMinuteUi.volume, oneMinuteLast.volume);
    assert.equal(oneMinuteUi.count, String(oneMinutePayload.candles.length));
    assert.ok(oneMinuteUi.canvas.width > 100 && oneMinuteUi.canvas.height > 100);
    assert.ok(oneMinuteUi.bars, "browser could not inspect the 1m chart batch");
    assert.equal(oneMinuteUi.bars.length, oneMinutePayload.candles.length);
    for (let i = 0; i < oneMinutePayload.candles.length; i++) {
      const source = oneMinutePayload.candles[i];
      const chart = oneMinuteUi.bars[i];
      assert.equal(chart.open_time, source.open_time, `1m chart open_time differs at candle ${i}`);
      for (const field of ["open", "high", "low", "close"]) {
        assert.equal(chart[field], Number(source[field]), `1m chart ${field} differs at candle ${i}`);
      }
      assert.equal(chart.volume, source.volume, `1m chart volume differs at candle ${i}`);
    }
    const oneMinutePixels = await page.evaluate(() => {
      const canvases = [...document.querySelectorAll("#chart canvas")];
      let green = 0;
      let red = 0;
      let sampled = 0;
      for (const canvas of canvases) {
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx || canvas.width === 0 || canvas.height === 0) continue;
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        for (let p = 0; p < pixels.length; p += 16) {
          const r = pixels[p], g = pixels[p + 1], b = pixels[p + 2], alpha = pixels[p + 3];
          if (alpha < 160) continue;
          sampled++;
          if (Math.abs(r - 54) < 35 && Math.abs(g - 201) < 45 && Math.abs(b - 143) < 45) green++;
          if (Math.abs(r - 241) < 35 && Math.abs(g - 107) < 45 && Math.abs(b - 117) < 45) red++;
        }
      }
      return { canvas_count: canvases.length, sampled_pixels: sampled, green_candle_color_pixels: green, red_candle_color_pixels: red };
    });
    const oneMinuteVisiblePixels = oneMinutePixels.green_candle_color_pixels + oneMinutePixels.red_candle_color_pixels;
    assert.ok(oneMinutePixels.canvas_count > 0 && oneMinuteVisiblePixels >= 8,
      "1m candlesticks are not visibly rendered: " + JSON.stringify(oneMinutePixels));
    const expectedOneMinuteStamp = new Date(oneMinuteLast.close_time).toISOString().replace("T", " ").replace(".000Z", " UTC");
    assert.equal(oneMinuteUi.stamp, expectedOneMinuteStamp, "1m displayed UTC time differs from source batch");
    const oneMinuteResponsiveViewports = [];
    for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1440, height: 1000 }]) {
      await page.setViewportSize(viewport);
      const minimumChartWidth = viewport.width <= 600 ? 200 : viewport.width <= 800 ? 550 : 900;
      await page.waitForFunction((minimum) => {
        const container = document.querySelector("#chart");
        const canvas = document.querySelector("#chart canvas");
        const rect = canvas?.getBoundingClientRect();
        return !!rect && rect.width > minimum && rect.width <= container.clientWidth + 1 &&
          document.documentElement.scrollWidth <= window.innerWidth + 1;
      }, minimumChartWidth, { timeout: 10000 });
      const layout = await page.evaluate(() => {
        const container = document.querySelector("#chart");
        const canvas = document.querySelector("#chart canvas");
        const rect = canvas?.getBoundingClientRect();
        return {
          viewportWidth: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          containerWidth: container.clientWidth,
          chartWidth: rect ? rect.width : 0,
          chartHeight: rect ? rect.height : 0,
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1
        };
      });
      assert.ok(layout.chartWidth > minimumChartWidth && layout.chartHeight > 200, "1m chart is not usable at viewport " + viewport.width + ": " + JSON.stringify(layout));
      assert.ok(layout.chartWidth <= layout.containerWidth + 1, "1m chart canvas did not resize to its container at viewport " + viewport.width + ": " + JSON.stringify(layout));
      assert.equal(layout.horizontalOverflow, false, "1m chart horizontal overflow at viewport " + viewport.width + ": " + JSON.stringify(layout));
      oneMinuteResponsiveViewports.push(layout);
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
      execution_instrument_mapping_verified: candlePayload.execution_instrument_mapping_verified,
      volume_semantics_contract: candlePayload.volume_semantics_contract,
      trade_count_available: candlePayload.trade_count_available,
      taker_buy_flow_available: candlePayload.taker_buy_flow_available,
      venue: candlePayload.venue,
      product: candlePayload.product,
      symbol: candlePayload.symbol,
      interval: candlePayload.interval,
      intervals_verified: {
        "15m": { candle_count: fifteenMinutePayload.candles.length, input_batch_sha256: fifteenMinutePayload.input_batch_sha256 },
        "1m": { candle_count: oneMinutePayload.candles.length, input_batch_sha256: oneMinutePayload.input_batch_sha256 }
      },
      input_batch_sha256: candlePayload.input_batch_sha256,
      strategy_v2_status_code: strategyV2StatusCode,
      strategy_v2_status: strategyV2Payload.status,
      strategy_v2_decision: strategyV2Payload.decision,
      strategy_v2_source: strategyV2Payload.source || "gateio_public_spot",
      strategy_v2_symbol: strategyV2Payload.symbol || "BTC_USDT",
      strategy_v2_execution_enabled: strategyV2Payload.execution_enabled,
      candle_count: candlePayload.candles.length,
      chart_canvas: oneMinuteUi.canvas,
      responsive_viewports: responsiveViewports,
      one_minute_responsive_viewports: oneMinuteResponsiveViewports,
      visible_candle_pixels: oneMinutePixels,
      external_chart_cdn_requested: externalChartCdnRequested,
      direct_market_data_request_from_browser: directMarketDataRequest,
      displayed_close_matches_source: true,
      displayed_volume_matches_source: true,
      chart_input_batch_matches_api_batch: true,
      chart_all_candles_match_api_batch: true,
      execution_enabled: false,
      logo_asset_response: logoAssetResponse,
      logo_rendered: !!ui.logo && ui.logo.complete && ui.logo.naturalWidth > 0 && ui.logo.naturalHeight > 0,
      message: oneMinuteUi.message
    };
    // A 200 response is not sufficient: a degraded batch must never remain visible as VALIDATED.
    const candleRouteMatcher = url => new URL(url).pathname === "/api/candles";
    await page.waitForFunction(() => !document.querySelector("#refresh")?.disabled, null, { timeout: 10000 });
    await page.route(candleRouteMatcher, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "gaps_present",
          source: "gateio_public_spot",
          source_reader: "global_market_data_reader_v1",
          venue: "gateio",
          product: "spot",
          symbol: "BTCUSDT",
          source_symbol: "BTC_USDT",
          symbol_mapping_verified: true,
          input_batch_sha256: "a".repeat(64),
          execution_enabled: false,
          orders_placed: false,
          gaps: [{ expected_open_time_ms: 1, next_observed_open_time_ms: 120001, missing_intervals: 1 }],
          candles: [{ open_time: 1, close_time: new Date().toISOString(), open: "1", high: "2", low: "1", close: "2", volume: "1" }],
          feature_ready: true,
          latest_age_seconds: 1,
          stream_status: "disabled",
          stream_reason: "test_fixture"
        })
      });
    });
    await page.locator("#refresh").click();
    await page.waitForFunction(() => {
      const message = document.querySelector("#message")?.textContent || "";
      return message.startsWith("FAIL CLOSED") &&
        document.querySelector("#price")?.textContent === "—" &&
        document.querySelector("#stamp")?.textContent === "—" &&
        document.querySelector("#volume")?.textContent === "—" &&
        document.querySelector("#count")?.textContent === "—";
    }, null, { timeout: 10000 });
    const gapStateUi = await page.evaluate(() => ({
      message: document.querySelector("#message")?.textContent || "",
      price: document.querySelector("#price")?.textContent || "",
      stamp: document.querySelector("#stamp")?.textContent || "",
      volume: document.querySelector("#volume")?.textContent || "",
      count: document.querySelector("#count")?.textContent || ""
    }));
    assert.ok(gapStateUi.message.includes("Persisted candle gaps detected"), "gapped API payload was not explicitly rejected");
    assert.deepEqual([gapStateUi.price, gapStateUi.stamp, gapStateUi.volume, gapStateUi.count], ["—", "—", "—", "—"]);
    await page.unroute(candleRouteMatcher);

    // Even a structurally valid HTTP 200 batch is rejected when its selected timeframe is stale.
    const staleRouteMatcher = url => new URL(url).pathname === "/api/candles";
    await page.waitForFunction(() => !document.querySelector("#refresh")?.disabled, null, { timeout: 10000 });
    await page.route(staleRouteMatcher, async route => {
      const requestUrl = new URL(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          source: "gateio_public_spot",
          source_reader: "global_market_data_reader_v1",
          venue: "gateio",
          product: "spot",
          symbol: "BTCUSDT",
          source_symbol: "BTC_USDT",
          symbol_mapping_verified: true,
          input_batch_sha256: "a".repeat(64),
          interval: requestUrl.searchParams.get("interval"),
          latest_age_seconds: 5000,
          execution_enabled: false,
          orders_placed: false,
          gaps: [],
          candles: [{ open_time: 1, close_time: new Date().toISOString(), open: "1", high: "2", low: "1", close: "2", volume: "1" }],
          feature_ready: true,
          stream_status: "disabled",
          stream_reason: "test_fixture"
        })
      });
    });
    await page.locator("#interval").selectOption("1h");
    await page.waitForFunction(() => {
      const message = document.querySelector("#message")?.textContent || "";
      return message.startsWith("FAIL CLOSED") && message.includes("Stale candle batch") &&
        document.querySelector("#price")?.textContent === "—" &&
        document.querySelector("#stamp")?.textContent === "—" &&
        document.querySelector("#volume")?.textContent === "—" &&
        document.querySelector("#count")?.textContent === "—";
    }, null, { timeout: 10000 });
    const staleTimeframeUi = await page.evaluate(() => ({
      message: document.querySelector("#message")?.textContent || "",
      price: document.querySelector("#price")?.textContent || "",
      stamp: document.querySelector("#stamp")?.textContent || "",
      volume: document.querySelector("#volume")?.textContent || "",
      count: document.querySelector("#count")?.textContent || ""
    }));
    assert.deepEqual([staleTimeframeUi.price, staleTimeframeUi.stamp, staleTimeframeUi.volume, staleTimeframeUi.count], ["—", "—", "—", "—"]);
    await page.unroute(staleRouteMatcher);
    evidence.stale_timeframe_fail_closed = true;
    evidence.stale_timeframe_ui = staleTimeframeUi;
    require("node:fs").writeFileSync(
      "artifacts/native-ohlcv-dashboard-gap-state-smoke.json",
      JSON.stringify({
        schema_version: 1,
        status: "PASS",
        simulated_http_status: 200,
        simulated_api_status: "gaps_present",
        ui_status: "FAIL_CLOSED",
        stale_chart_values_cleared: true,
        execution_enabled: false
      }, null, 2) + "\n"
    );
    evidence.gap_state_fail_closed = true;
    evidence.gap_state_ui = gapStateUi;
    require("node:fs").writeFileSync("artifacts/native-ohlcv-dashboard-browser-smoke.json", JSON.stringify(evidence, null, 2) + "\n");
    process.stdout.write(JSON.stringify({ ...evidence, gap_state_fail_closed: true, gap_state_ui: gapStateUi }) + "\n");
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(String(error.stack || error) + "\n");
  process.exit(1);
});
