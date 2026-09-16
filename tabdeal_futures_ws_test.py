import csv
import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone

import websocket


# ============================================================
# TABDEAL BTC/USDT FUTURES COLLECTOR
# ============================================================

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"

OUTPUT_FILE = "data/trades.csv"
ARCHIVE_DIR = "data/archive"

RECONNECT_DELAY = 5

# EXACT COLLECTION TIME: 5 hours 20 minutes
RUN_SECONDS = 5 * 60 * 60 + 20 * 60

# Git checkpoint every 20 minutes
CHECKPOINT_SECONDS = 20 * 60

# ============================================================
# CSV SIZE CONTROL
# ============================================================

# Keep only the newest N trades in the active CSV.
# Older trades are moved to data/archive/
MAX_ACTIVE_ROWS = 150_000

# When rotating, move this many old rows to archive.
ARCHIVE_BATCH_ROWS = 50_000


# ============================================================
# GLOBAL STATE
# ============================================================

running = True

last_sequence = None
trade_count = 0
active_row_count = 0

csv_file = None
csv_writer = None

last_checkpoint_time = time.time()

CSV_HEADER = [
    "symbol",
    "price",
    "amount",
    "side",
    "updated",
    "sequence"
]


# ============================================================
# LOAD LAST SEQUENCE
# ============================================================

def load_last_sequence():
    """
    Read the last saved sequence from the active CSV.

    The active CSV always contains the newest trades, so its
    last row is the correct continuation point.
    """

    if not os.path.exists(OUTPUT_FILE):
        return None

    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

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


# ============================================================
# COUNT ACTIVE ROWS
# ============================================================

def count_active_rows():
    """
    Count current data rows in active CSV.
    """

    if not os.path.exists(OUTPUT_FILE):
        return 0

    count = 0

    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            reader = csv.reader(f)

            next(reader, None)

            for _ in reader:
                count += 1

    except Exception as e:
        print(
            f"Could not count active rows: {e}",
            flush=True
        )

    return count


# ============================================================
# OPEN CSV
# ============================================================

def open_csv():
    global csv_file
    global csv_writer
    global active_row_count

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
        exist_ok=True
    )

    os.makedirs(
        ARCHIVE_DIR,
        exist_ok=True
    )

    file_exists = os.path.exists(OUTPUT_FILE)

    file_empty = (
        not file_exists
        or os.path.getsize(OUTPUT_FILE) == 0
    )

    csv_file = open(
        OUTPUT_FILE,
        "a",
        newline="",
        encoding="utf-8"
    )

    csv_writer = csv.writer(csv_file)

    if file_empty:

        csv_writer.writerow(CSV_HEADER)

        csv_file.flush()

        active_row_count = 0

    else:

        active_row_count = count_active_rows()

    print(
        f"Active CSV rows: {active_row_count}",
        flush=True
    )


# ============================================================
# CLOSE CSV
# ============================================================

def close_csv():
    global csv_file

    if csv_file:

        try:
            csv_file.flush()
            csv_file.close()

        except Exception:
            pass

        csv_file = None


# ============================================================
# ARCHIVE FILE NAME
# ============================================================

def create_archive_name():

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    return os.path.join(
        ARCHIVE_DIR,
        f"trades_archive_{timestamp}.csv"
    )


# ============================================================
# ROTATE ACTIVE CSV
# ============================================================

def rotate_active_csv():
    """
    Keep only the newest MAX_ACTIVE_ROWS trades.

    Oldest rows are moved to an archive CSV.

    No trade is deleted.
    """

    global csv_file
    global csv_writer
    global active_row_count

    if active_row_count <= MAX_ACTIVE_ROWS:
        return

    print(
        "=== CSV SIZE LIMIT REACHED ===",
        flush=True
    )

    print(
        f"Active rows: {active_row_count}",
        flush=True
    )

    print(
        f"Maximum active rows: {MAX_ACTIVE_ROWS}",
        flush=True
    )

    close_csv()

    temp_file = OUTPUT_FILE + ".tmp"

    archive_file = create_archive_name()

    rows_to_archive = min(
        ARCHIVE_BATCH_ROWS,
        active_row_count - MAX_ACTIVE_ROWS
    )

    print(
        f"Archiving {rows_to_archive} old rows...",
        flush=True
    )

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as source, \
        open(
            temp_file,
            "w",
            encoding="utf-8",
            newline=""
        ) as active_temp, \
        open(
            archive_file,
            "w",
            encoding="utf-8",
            newline=""
        ) as archive_temp:

            reader = csv.reader(source)

            active_writer = csv.writer(active_temp)

            archive_writer = csv.writer(
                archive_temp
            )

            header = next(
                reader,
                CSV_HEADER
            )

            active_writer.writerow(header)

            archive_writer.writerow(header)

            archived = 0
            kept = 0

            for row in reader:

                if (
                    archived < rows_to_archive
                ):

                    archive_writer.writerow(row)

                    archived += 1

                else:

                    active_writer.writerow(row)

                    kept += 1

        # Replace original active CSV
        os.replace(
            temp_file,
            OUTPUT_FILE
        )

        active_row_count = kept

        print(
            "=== CSV ROTATION COMPLETE ===",
            flush=True
        )

        print(
            f"Archived rows: {archived}",
            flush=True
        )

        print(
            f"Active rows: {active_row_count}",
            flush=True
        )

        print(
            f"Archive: {archive_file}",
            flush=True
        )

        # Re-open active CSV
        csv_file = open(
            OUTPUT_FILE,
            "a",
            newline="",
            encoding="utf-8"
        )

        csv_writer = csv.writer(
            csv_file
        )

        csv_file.flush()

    except Exception as e:

        print(
            f"=== CSV ROTATION ERROR: {e} ===",
            flush=True
        )

        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass

        # Re-open original CSV if possible
        try:

            csv_file = open(
                OUTPUT_FILE,
                "a",
                newline="",
                encoding="utf-8"
            )

            csv_writer = csv.writer(
                csv_file
            )

        except Exception as reopen_error:

            print(
                f"Could not reopen CSV: {reopen_error}",
                flush=True
            )


# ============================================================
# GIT COMMAND
# ============================================================

def run_git(command):
    return subprocess.run(
        command,
        check=True
    )


# ============================================================
# GIT CHECKPOINT
# ============================================================

def git_checkpoint():

    global last_checkpoint_time

    try:

        if csv_file:
            csv_file.flush()

        print(
            "=== GIT CHECKPOINT START ===",
            flush=True
        )

        run_git([
            "git",
            "config",
            "user.name",
            "github-actions[bot]"
        ])

        run_git([
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com"
        ])

        # Get latest remote state
        run_git([
            "git",
            "fetch",
            "origin",
            "main"
        ])

        # Synchronize local branch with remote
        run_git([
            "git",
            "reset",
            "--soft",
            "origin/main"
        ])

        # IMPORTANT:
        # Add both active CSV and archive files.
        run_git([
            "git",
            "add",
            OUTPUT_FILE,
            ARCHIVE_DIR
        ])

        result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--quiet"
            ]
        )

        if result.returncode == 0:

            print(
                "=== NO NEW DATA FOR CHECKPOINT ===",
                flush=True
            )

            last_checkpoint_time = time.time()

            return True

        run_git([
            "git",
            "commit",
            "-m",
            "Checkpoint Tabdeal BTC_USDT trades"
        ])

        run_git([
            "git",
            "push",
            "origin",
            "main"
        ])

        print(
            "=== GIT CHECKPOINT COMPLETE ===",
            flush=True
        )

        last_checkpoint_time = time.time()

        return True

    except Exception as e:

        print(
            f"=== CHECKPOINT ERROR: {e} ===",
            flush=True
        )

        return False


# ============================================================
# MAYBE CHECKPOINT
# ============================================================

def maybe_checkpoint():

    if (
        time.time() - last_checkpoint_time
        >= CHECKPOINT_SECONDS
    ):

        git_checkpoint()


# ============================================================
# SAVE TRADE
# ============================================================

def save_trade(trade):

    global last_sequence
    global trade_count
    global active_row_count

    sequence_raw = trade.get(
        "sequence"
    )

    if sequence_raw is None:
        return

    try:

        sequence = int(
            sequence_raw
        )

    except (
        ValueError,
        TypeError
    ):

        return

    # ========================================================
    # DUPLICATE / OLD SEQUENCE PROTECTION
    # ========================================================

    if (
        last_sequence is not None
        and sequence <= last_sequence
    ):

        return

    # ========================================================
    # SAVE TRADE
    # ========================================================

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

    active_row_count += 1

    print(
        f"SAVED | "
        f"{trade.get('updated')} | "
        f"{trade.get('side_name')} | "
        f"{trade.get('price')} | "
        f"{trade.get('amount')} | "
        f"seq={sequence}",
        flush=True
    )

    # ========================================================
    # CHECK CSV SIZE
    # ========================================================

    if active_row_count > MAX_ACTIVE_ROWS:

        rotate_active_csv()

    # ========================================================
    # GIT CHECKPOINT
    # ========================================================

    maybe_checkpoint()


# ============================================================
# STOP COLLECTOR
# ============================================================

def stop_collector(
    signum=None,
    frame=None
):

    global running

    print(
        "\n=== STOP SIGNAL RECEIVED ===",
        flush=True
    )

    running = False


signal.signal(
    signal.SIGINT,
    stop_collector
)

signal.signal(
    signal.SIGTERM,
    stop_collector
)


# ============================================================
# WEBSOCKET OPEN
# ============================================================

def on_open(ws):

    print(
        "=== CONNECTED ===",
        flush=True
    )

    print(
        f"=== SUBSCRIBE {SYMBOL} ===",
        flush=True
    )

    ws.send(SYMBOL)


# ============================================================
# WEBSOCKET MESSAGE
# ============================================================

def on_message(
    ws,
    message
):

    try:

        data = json.loads(
            message
        )

        if "trade" in data:

            save_trade(
                data["trade"]
            )

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


# ============================================================
# WEBSOCKET ERROR
# ============================================================

def on_error(
    ws,
    error
):

    print(
        f"=== WEBSOCKET ERROR === {error}",
        flush=True
    )


# ============================================================
# WEBSOCKET CLOSE
# ============================================================

def on_close(
    ws,
    close_status_code,
    close_msg
):

    print(
        f"=== WEBSOCKET CLOSED === "
        f"code={close_status_code} "
        f"message={close_msg}",
        flush=True
    )


# ============================================================
# CLOSE WEBSOCKET
# ============================================================

def close_websocket(ws):

    try:

        print(
            "=== COLLECTION TIMER: CLOSING WEBSOCKET ===",
            flush=True
        )

        ws.close()

    except Exception as e:

        print(
            f"WEBSOCKET CLOSE ERROR: {e}",
            flush=True
        )


# ============================================================
# COLLECT
# ============================================================

def collect():

    global running

    start_time = time.monotonic()

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
        f"Archive: {ARCHIVE_DIR}",
        flush=True
    )

    print(
        "Duration: 5h 20m",
        flush=True
    )

    print(
        "Checkpoint: every 20 minutes",
        flush=True
    )

    print(
        f"Maximum active CSV rows: "
        f"{MAX_ACTIVE_ROWS}",
        flush=True
    )

    while running:

        elapsed = (
            time.monotonic()
            - start_time
        )

        if elapsed >= RUN_SECONDS:

            print(
                "=== COLLECTION TIME COMPLETE ===",
                flush=True
            )

            break

        remaining = (
            RUN_SECONDS
            - elapsed
        )

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

            timer = threading.Timer(

                remaining,

                close_websocket,

                args=(ws,)

            )

            timer.daemon = True

            timer.start()

            ws.run_forever(

                ping_interval=20,

                ping_timeout=10

            )

            timer.cancel()

        except Exception as e:

            print(
                f"COLLECTOR ERROR: {e}",
                flush=True
            )

        elapsed = (
            time.monotonic()
            - start_time
        )

        if elapsed >= RUN_SECONDS:

            print(
                "=== COLLECTION TIME COMPLETE ===",
                flush=True
            )

            break

        if running:

            print(
                f"=== RECONNECTING IN "
                f"{RECONNECT_DELAY}s ===",
                flush=True
            )

            sleep_time = min(

                RECONNECT_DELAY,

                RUN_SECONDS - elapsed

            )

            if sleep_time > 0:

                time.sleep(
                    sleep_time
                )

    running = False

    print(
        f"=== TOTAL TRADES COLLECTED: "
        f"{trade_count} ===",
        flush=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global last_sequence

    last_sequence = (
        load_last_sequence()
    )

    if last_sequence is not None:

        print(
            f"Last saved sequence: "
            f"{last_sequence}",
            flush=True
        )

    else:

        print(
            "No previous sequence found.",
            flush=True
        )

    open_csv()

    try:

        collect()

    finally:

        close_csv()

        print(
            "=== FINAL GIT CHECKPOINT ===",
            flush=True
        )

        git_checkpoint()

        print(
            "=== CSV CLOSED SAFELY ===",
            flush=True
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
