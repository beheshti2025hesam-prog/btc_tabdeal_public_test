const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");

const baseUrl = process.env.HES_DASHBOARD_SMOKE_BASE_URL || "http://127.0.0.1:8765";
const token = process.env.HES_MOTHER_CHAT_TOKEN;
if (!token) throw new Error("HES_MOTHER_CHAT_TOKEN is required");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const evidence = { schema_version: 1, status: "PASS", locales: [], execution_enabled: false, orders_placed: false };
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, locale: "en-US" });
    await page.goto(baseUrl + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.locator("#motherChatToken").fill(token);
    await page.locator("#motherChatUnlock").click();
    await page.locator("#motherChatWorkspace").waitFor({ state: "visible", timeout: 10000 });

    const cases = [
      { language: "en", message: "status", expected: "en", direction: "ltr" },
      { language: "fr", message: "status", expected: "fr", direction: "ltr" },
      { language: "fa", message: "status", expected: "fa", direction: "rtl" },
      { language: "auto", message: "وضعیت سیستم", expected: "fa", direction: "rtl" },
      { language: "auto", message: "Warum ist die Entscheidung NO_TRADE?", expected: "de", direction: "ltr" }
    ];
    for (const item of cases) {
      await page.locator("#motherChatLanguage").selectOption(item.language);
      await page.locator("#motherChatInput").fill(item.message);
      const responsePromise = page.waitForResponse(response =>
        new URL(response.url()).pathname === "/api/mother-chat" &&
        response.request().method() === "POST"
      );
      await page.locator("#motherChatSend").click();
      const response = await responsePromise;
      assert.equal(response.status(), 200, "chat request failed for " + item.language);
      const body = await response.json();
      assert.equal(body.language, item.expected, "wrong response language for " + item.language);
      assert.equal(body.direction, item.direction, "wrong text direction for " + item.language);
      assert.equal(body.external_llm_used, false);
      assert.equal(body.execution_enabled, false);
      assert.equal(body.orders_placed, false);
      const assistant = page.locator(".mother-chat-message.mother").last();
      await assistant.waitFor({ state: "visible", timeout: 5000 });
      assert.equal(await assistant.getAttribute("lang"), item.expected);
      assert.equal(await assistant.getAttribute("dir"), item.direction);
      const userBubble = page.locator(".mother-chat-message.user").last();
      if (item.language === "fa" && item.message === "status") {
        assert.equal(await userBubble.getAttribute("dir"), "ltr", "response locale must not rewrite the prompt direction");
      }
      assert.ok((await assistant.locator("p").textContent()).trim().length > 0);
      evidence.locales.push({ selected: item.language, detected_or_selected: body.language, direction: body.direction, intent: body.intent, status: body.status });
    }

    await page.locator("#motherChatLogout").click();
    await page.locator("#motherChatWorkspace").waitFor({ state: "hidden", timeout: 5000 });
    evidence.logout = "PASS";
    fs.mkdirSync("artifacts", { recursive: true });
    fs.writeFileSync("artifacts/mother-chat-multilingual-browser-smoke.json", JSON.stringify(evidence, null, 2) + "\n");
    process.stdout.write(JSON.stringify(evidence) + "\n");
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(String(error.stack || error) + "\n");
  process.exit(1);
});
