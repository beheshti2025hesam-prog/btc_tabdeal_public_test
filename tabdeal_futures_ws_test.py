import time

from tabdeal.websocket_client import FutureWebsocketClient


def handler(message):
    print("=== MESSAGE RECEIVED ===")
    print(message)


print("=== TABDEAL OFFICIAL FUTURES SDK TEST ===")

try:
    ws = FutureWebsocketClient()

    print("=== SDK CLIENT CREATED ===")

    ws.market_order_book(
        symbol="btcusdt",
        id=1,
        callback=handler,
    )

    print("=== SUBSCRIPTION SENT ===")
    print("Waiting for Futures order book data...")

    time.sleep(15)

    print("=== TEST FINISHED ===")

except Exception as e:
    print("=== ERROR ===")
    print(type(e).__name__, ":", e)
