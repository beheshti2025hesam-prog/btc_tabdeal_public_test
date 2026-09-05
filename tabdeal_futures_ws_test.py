import json
import websocket

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"

print("=== TABDEAL FUTURES TRADE TEST ===")
print("URL:", WS_URL)


def on_open(ws):
    print("=== CONNECTED ===")
    print("=== SUBSCRIBE BTC_USDT ===")

    # Futures Broadcast uses plain text, not JSON
    ws.send("BTC_USDT")


def on_message(ws, message):
    print("=== TRADE MESSAGE ===")
    print(message)

    # Try to decode the JSON message
    try:
        data = json.loads(message)
        print("=== PARSED ===")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print("Could not parse message:", e)


def on_error(ws, error):
    print("=== WEBSOCKET ERROR ===")
    print(error)


def on_close(ws, close_status_code, close_msg):
    print("=== WEBSOCKET CLOSED ===")
    print("Code:", close_status_code)
    print("Message:", close_msg)


ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()
