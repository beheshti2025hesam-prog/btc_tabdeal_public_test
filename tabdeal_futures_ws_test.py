import json
import time
import websocket


WS_URL = "wss://api1.tabdeal.org/special_margin/stream/"


def on_open(ws):
    print("=== WEBSOCKET CONNECTED ===")

    payload = {
        "method": "SUBSCRIBE",
        "params": [
            "btcusdt@trade",
            "btcusdt@aggTrade",
        ],
        "id": 1
    }

    print("SUBSCRIBE:")
    print(json.dumps(payload))

    ws.send(json.dumps(payload))


def on_message(ws, message):
    print("=" * 70)
    print("MESSAGE RECEIVED:")
    print(message)


def on_error(ws, error):
    print("=" * 70)
    print("WEBSOCKET ERROR:")
    print(error)


def on_close(ws, close_status_code, close_msg):
    print("=" * 70)
    print("WEBSOCKET CLOSED")
    print("Code:", close_status_code)
    print("Message:", close_msg)


print("=== TABDEAL FUTURES WEBSOCKET TEST ===")
print("URL:", WS_URL)
print()

ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()
