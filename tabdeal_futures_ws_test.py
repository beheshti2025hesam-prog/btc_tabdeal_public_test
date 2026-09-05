import websocket

WS_URL = "wss://api1.tabdeal.org/special_margin/stream/"

print("=== TABDEAL FUTURES WEBSOCKET CONNECTION TEST ===")
print("URL:", WS_URL)

try:
    ws = websocket.create_connection(
        WS_URL,
        timeout=10,
        origin="https://api1.tabdeal.org"
    )

    print("=== CONNECTED SUCCESSFULLY ===")
    print("WebSocket connection established.")

    ws.close()

except Exception as e:
    print("=== CONNECTION FAILED ===")
    print(type(e).__name__, ":", e)
