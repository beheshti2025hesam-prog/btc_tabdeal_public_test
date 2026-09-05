import json
import time
import websocket

WS_URL = "wss://api1.tabdeal.org/special_margin/stream/"

print("=== TABDEAL FUTURES DEPTH TEST ===")
print("URL:", WS_URL)

try:
    ws = websocket.create_connection(
        WS_URL,
        timeout=10,
        origin="https://api1.tabdeal.org"
    )

    print("=== CONNECTED ===")

    payload = {
        "method": "SUBSCRIBE",
        "params": [
            "btcusdt@depth@2000ms"
        ],
        "id": 1
    }

    print("=== SUBSCRIBE ===")
    print(json.dumps(payload))

    ws.send(json.dumps(payload))

    start = time.time()

    while time.time() - start < 10:
        try:
            message = ws.recv()

            if message:
                print("=== MESSAGE RECEIVED ===")
                print(message)

        except websocket.WebSocketTimeoutException:
            print("No message received yet...")

    ws.close()

except Exception as e:
    print("=== ERROR ===")
    print(type(e).__name__, ":", e)
