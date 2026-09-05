import csv
import json
import os
import time
from datetime import datetime, timezone

import websocket


WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
OUTPUT_FILE = "data/trades.csv"

RECONNECT_DELAY = 5


os.makedirs("data", exist_ok=True)


def get_last_sequence():
    if not os.path.exists(OUTPUT_FILE):
        return None

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            return None

        return rows[-1].get("sequence")

    except Exception as e:
        print(f"Could not read last sequence: {e}", flush=True)
        return None


def save_trade(trade):
    sequence = str(trade.get("sequence", ""))

    if not sequence:
        return

    last_sequence = get_last_sequence()

    # جلوگیری از ذخیره Trade تکراری
    if last_sequence == sequence:
        print(
            f"DUPLICATE IGNORED | sequence={sequence}",
            flush=True
        )
        return

    file_exists = os.path.exists(OUTPUT_FILE)

    with open(
        OUTPUT_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

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
            sequence
        ])

        f.flush()

    print(
        f"SAVED | "
        f"{trade.get('updated')} | "
        f"{trade.get('side_name')} | "
        f"{trade.get('price')} | "
        f"{trade.get('amount')} | "
        f"seq={sequence}",
        flush=True
    )


def on_open(ws):
    print("=== CONNECTED ===", flush=True)
    print(f"=== SUBSCRIBE {SYMBOL} ===", flush=True)

    ws.send(SYMBOL)


def on_message(ws, message):
    try:
        data = json.loads(message)

        if "trade" in data:
            save_trade(data["trade"])

        elif "order" in data:
            print("ORDER EVENT IGNORED", flush=True)

        else:
            print(
                f"OTHER MESSAGE: {message}",
                flush=True
            )

    except Exception as e:
        print(
            f"MESSAGE ERROR: {e}",
            flush=True
        )


def on_error(ws, error):
    print(
        f"=== WEBSOCKET ERROR === {error}",
        flush=True
    )


def on_close(ws, close_status_code, close_msg):
    print(
        f"=== WEBSOCKET CLOSED === "
        f"code={close_status_code} "
        f"message={close_msg}",
        flush=True
    )


def collect_forever():
    print("=== TABDEAL FUTURES COLLECTOR ===", flush=True)
    print(f"Symbol: {SYMBOL}", flush=True)
    print(f"Output: {OUTPUT_FILE}", flush=True)

    while True:
        try:
            print(
                f"=== CONNECTING {WS_URL} ===",
                flush=True
            )

            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            ws.run_forever(
                ping_interval=20,
                ping_timeout=10
            )

        except Exception as e:
            print(
                f"COLLECTOR ERROR: {e}",
                flush=True
            )

        print(
            f"=== RECONNECTING IN {RECONNECT_DELAY}s ===",
            flush=True
        )

        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    collect_forever()
