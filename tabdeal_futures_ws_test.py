import inspect
import tabdeal.websocket_client as wc

print("=== TABDEAL WEBSOCKET SDK INSPECTION ===")
print("Module:", wc.__file__)
print()

print("=== AVAILABLE WEBSOCKET CLASSES ===")
for name in dir(wc):
    if "Websocket" in name:
        print(name)

print()
print("=== FUTURE WEBSOCKET SOURCE ===")

if hasattr(wc, "FutureWebsocketClient"):
    print(inspect.getsource(wc.FutureWebsocketClient))
else:
    print("FutureWebsocketClient NOT FOUND")

print()
print("=== MARKET ORDER BOOK SOURCE ===")

if hasattr(wc, "FutureWebsocketClient"):
    print(inspect.getsource(wc.FutureWebsocketClient.market_order_book))
