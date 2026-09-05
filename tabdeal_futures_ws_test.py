import csv
import json
import os
import websocket

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
OUTPUT_FILE = "data/trades.csv"


os.makedirs("data", exist_ok=True)


def save_trade(trade):
    file_exists = os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "symbol",
                "price",
                "amount",
                "side",
                "updated",
                "sequence"
            ])

        writer.writerow([
            trade.get("symbol"),
            trade.get("price"),
            trade.get("amount"),
            trade.get("side_name"),
            trade.get("updated"),
            trade.get("sequence")
        ])

        f.flush()

    print(
        f"SAVED | "
        f"{trade.get('updated')} | "
        f"{trade.get('side_name')} | "
        f"{trade.get('price')} | "
        f"{trade.get('amount')}",
        flush=True
    )


def on_open(ws):
    print("=== CONNECTED ===", flush=True)
    print(f"=== SUBSCRIBE {SYMBOL} ===", flush=True)

    # Tabdeal Futures Broadcast uses plain text subscription
    ws.send(SYMBOL)


def on_message(ws, message):
    try:
        data = json.loads(message)

        # Normal trade message
        if "trade" in data:
            save_trade(data["trade"])

        # Ignore other message types
        elif "order" in data:
            print("ORDER EVENT IGNORED", flush=True)

        else:
            print("OTHER MESSAGE:", message, flush=True)

    except Exception as e:
        print("MESSAGE ERROR:", e, flush=True)


def on_error(ws, error):
    print("=== WEBSOCKET ERROR ===", flush=True)
    print(error, flush=True)


def on_close(ws, close_status_code, close_msg):
    print("=== WEBSOCKET CLOSED ===", flush=True)
    print("Code:", close_status_code, flush=True)
    print("Message:", close_msg, flush=True)


print("=== TABDEAL FUTURES TRADE COLLECTOR ===", flush=True)
print("URL:", WS_URL, flush=True)
print("Symbol:", SYMBOL, flush=True)
print("Output:", OUTPUT_FILE, flush=True)


ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()
