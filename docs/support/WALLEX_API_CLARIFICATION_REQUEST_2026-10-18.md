# Wallex API clarification request — 2026-10-18

**Recipient identified from Wallex's official public Telegram contact notice:** `info@wallex.market`  
**Suggested subject:** Technical clarification required: UDF candle volume semantics and public WebSocket contract

## Message

با سلام و احترام،

در حال بررسی فنی و صرفاً خواندنی API عمومی والکس برای پروژه پژوهشی HES Trade Agent هستیم. پیش از پذیرش داده‌ها برای هرگونه قابلیت وابسته به حجم یا جریان معاملات، لطفاً موارد زیر را به‌صورت مکتوب و با ارجاع به قرارداد رسمی API روشن فرمایید.

### ۱) معنای حجم کندل‌ها
در `GET https://api.wallex.ir/v1/udf/history`، فیلد `v` دقیقاً چه واحد و معنای تجمیعی دارد؟ آیا حجم دارایی پایه است، حجم مظنه است، یا تعریف دیگری دارد؟

در مقایسهٔ هم‌بازه، OHLC کندل‌های بسته با تجمیع معاملات عمومی هم‌خوان بوده، اما مقدار `v` در نمونهٔ بررسی‌شده دقیقاً دو برابر مجموع `quantity` معاملات REST بوده است. لطفاً توضیح دهید:
- آیا `v` و `/v1/trades.quantity` واحد و دامنهٔ تجمیع یکسان دارند؟
- آیا معاملات خرید و فروش جداگانه یا دو بار در حجم کندل شمرده می‌شوند؟
- فیلدهای `sum`، `24h_volume` و `24h_quoteVolume` چه رابطهٔ دقیقی با این فیلدها دارند؟
- آیا `/v1/trades` فقط آخرین تعداد محدودی معامله را برمی‌گرداند؟ اگر بله، مسیر رسمی دریافت تاریخچهٔ کامل و قابل بازپخش معاملات چیست؟

### ۲) قرارداد رسمی WebSocket
مستندات عمومی نمونهٔ Socket.IO سازگار با نسخهٔ 2.5.0، رویداد `Broadcaster` و کانال‌های `SYMBOL@trade` و `SYMBOL@buyDepth / sellDepth` را نشان می‌دهد. با این حال، handshake مسیر `/socket.io/` از میزبان مشاهده‌گر ما HTTP 503 برگرداند.

لطفاً تأیید کنید:
- مسیر و نسخهٔ رسمی فعلی WebSocket/Socket.IO برای داده‌های عمومی چیست؟
- آیا مسیر `wss://api.wallex.ir/ws` نیز رسمی و پشتیبانی‌شده است؟ در صورت مثبت بودن، قرارداد handshake، heartbeat، subscribe، event framing و چرخهٔ reconnect آن را ارائه فرمایید.
- آیا پیام‌های trade یا depth دارای شناسهٔ یکتا، sequence/update range یا تضمین replay/ordering هستند؟ لطفاً دامنهٔ تضمین‌ها را برای هر کانال مشخص کنید.

### ۳) شواهد و پذیرش
در صورت امکان، لطفاً یک پاسخ نمونهٔ رسمی و قابل بازتولید یا فایل fixture کامل برای یک بازهٔ زمانی مشخص ارائه کنید تا بتوانیم آن را با هش SHA-256 و پوشش زمانی کامل بررسی کنیم. تا دریافت پاسخ معتبر، هیچ ضریب اصلاح حجم (از جمله تقسیم بر دو) اعمال نخواهد شد و هیچ داده‌ای برای فعال‌سازی معامله استفاده نمی‌شود.

با سپاس،
تیم فنی HES Trade Agent

## Evidence references

- Official API reference: https://api-docs.wallex.ir/
- Pinned candle-volume investigation: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/issues/322
- Pinned WebSocket/session-isolation investigation: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/issues/323
- Official Socket.IO reachability probe: `evidence/wallex_official_socketio_reachability_20261018.json`

## Sending status

**Draft only — not sent.** The current connected integrations do not expose an authorized email-sending account. Do not mark this request as delivered until a sending action returns a message ID or Wallex replies through an official support channel.
