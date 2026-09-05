import csv
import json
import os
import signal
import time

import websocket


WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
OUTPUT_FILE = "data/trades.csv"

RECONNECT_DELAY = 5

# مدت اجرای Collector
# 5 ساعت و 45 دقیقه
RUN_SECONDS = 5 * 60 * 60 + 45 * 60


os.makedirs("data", exist_ok=True)

running = True
last_sequence = None
trade_count = 0

csv_file = None
csv_writer = None


def load_last_sequence():
    """فقط یک بار در شروع، آخرین sequence ذخیره‌شده را بخوان."""
    if not os.path.exists(OUTPUT_FILE):
        return None

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            last_row = None

            for row in reader:
                last_row = row

            if last_row and last_row.get("sequence"):
                return int(last_row["sequence"])

    except Exception as e:
        print(
            f"Could not read last sequence: {e}",
            flush=True
        )

    return None


def open_csv():
    global csv_file, csv_writer

    file_exists = os.path.exists(OUTPUT_FILE)
    file_empty = not file_exists or os.path.getsize(OUTPUT_FILE) == 0

    csv_file = open(
        OUTPUT_FILE,
        "a",
        newline="",
        encoding="utf-8"
    )

    csv_writer = csv.writer(csv_file)

    if file_empty:
        csv_writer.writerow([
            "symbol",
            "price",
            "amount",
            "side",
            "updated",
            "sequence"
        ])

        csv_file.flush()


def close_csv():
    global csv_file

    if csv_file:
        try:
            csv_file.flush()
            csv_file.close()
        except Exception:
            pass

        csv_file = None


def save_trade(trade):
    global last_sequence
    global trade_count

    sequence_raw = trade.get("sequence")

    if sequence_raw is None:
        return

    try:
        sequence = int(sequence_raw)
    except (ValueError, TypeError):
        return

    # جلوگیری از ذخیره Trade تکراری
    if last_sequence is not None and sequence <= last_sequence:
        return

    csv_writer.writerow([
        trade.get("symbol"),
        trade.get("price"),
        trade.get("amount"),
        trade.get("side_name"),
        trade.get("updated"),
        sequence
    ])

    csv_file.flush()

    last_sequence = sequence
    trade_count += 1

    print(
        f"SAVED | "
        f"{trade.get('updated')} | "
        f"{trade.get('side_name')} | "
        f"{trade.get('price')} | "
        f"{trade.get('amount')} | "
        f"seq={sequence}",
        flush=True
    )


def stop_collector(signum=None, frame=None):
    global running

    print(
        "\n=== STOP SIGNAL RECEIVED ===",
        flush=True
    )

    running = False


signal.signal(signal.SIGINT, stop_collector)
signal.signal(signal.SIGTERM, stop_collector)


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
            print(
                "ORDER EVENT IGNORED",
                flush=True
            )

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
    global running

    start_time = time.time()

    print(
        "=== TABDEAL FUTURES COLLECTOR ===",
        flush=True
    )

    print(
        f"Symbol: {SYMBOL}",
        flush=True
    )

    print(
        f"Output: {OUTPUT_FILE}",
        flush=True
    )

    print(
        f"Duration: {RUN_SECONDS // 3600}h "
        f"{(RUN_SECONDS % 3600) // 60}m",
        flush=True
    )

    while running:

        elapsed = time.time() - start_time

        if elapsed >= RUN_SECONDS:
            print(
                "=== COLLECTION TIME COMPLETE ===",
                flush=True
            )
            break

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

        if running:
            print(
                f"=== RECONNECTING IN "
                f"{RECONNECT_DELAY}s ===",
                flush=True
            )

            time.sleep(RECONNECT_DELAY)

    print(
        f"=== TOTAL TRADES COLLECTED: "
        f"{trade_count} ===",
        flush=True
    )


def main():
    global last_sequence

    last_sequence = load_last_sequence()

    if last_sequence is not None:
        print(
            f"Last saved sequence: {last_sequence}",
            flush=True
        )
    else:
        print(
            "No previous sequence found.",
            flush=True
        )

    open_csv()

    try:
        collect_forever()

    finally:
        close_csv()

        print(
            "=== CSV CLOSED SAFELY ===",
            flush=True
        )


if __name__ == "__main__":
    main()
