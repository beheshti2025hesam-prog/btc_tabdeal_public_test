import csv
import json
import os
import signal
import subprocess
import threading
import time

import websocket


WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"

OUTPUT_FILE = "data/trades.csv"
ARCHIVE_DIR = "data/archive"

RECONNECT_DELAY = 5

# EXACT COLLECTION TIME: 5 hours 20 minutes
RUN_SECONDS = 5 * 60 * 60 + 20 * 60

# Git checkpoint every 20 minutes
CHECKPOINT_SECONDS = 20 * 60

# Active CSV size management
MAX_ACTIVE_ROWS = 150000
ARCHIVE_BATCH_ROWS = 50000


running = True
last_sequence = None
trade_count = 0

active_rows = 0

csv_file = None
csv_writer = None

current_ws = None

last_checkpoint_time = time.time()


# ============================================================
# CSV / FILE UTILITIES
# ============================================================

def flush_csv():
    global csv_file

    if csv_file:
        try:
            csv_file.flush()
            os.fsync(csv_file.fileno())
        except Exception as e:
            print(
                f"CSV FLUSH ERROR: {e}",
                flush=True
            )


def load_last_sequence():
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


def count_active_rows():
    if not os.path.exists(OUTPUT_FILE):
        return 0

    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            reader = csv.reader(f)

            next(reader, None)

            return sum(
                1
                for _ in reader
            )

    except Exception as e:
        print(
            f"Could not count active CSV rows: {e}",
            flush=True
        )

        return 0


def open_csv():
    global csv_file
    global csv_writer
    global active_rows

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
        exist_ok=True
    )

    os.makedirs(
        ARCHIVE_DIR,
        exist_ok=True
    )

    file_exists = os.path.exists(
        OUTPUT_FILE
    )

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

    csv_writer = csv.writer(
        csv_file
    )

    if file_empty:
        csv_writer.writerow([
            "symbol",
            "price",
            "amount",
            "side",
            "updated",
            "sequence"
        ])

        flush_csv()

        active_rows = 0

    else:
        active_rows = count_active_rows()

    print(
        f"Active CSV rows: {active_rows}",
        flush=True
    )


def close_csv():
    global csv_file
    global csv_writer

    if csv_file:
        try:
            flush_csv()
            csv_file.close()
        except Exception:
            pass

    csv_file = None
    csv_writer = None


# ============================================================
# ARCHIVE MANAGEMENT
# ============================================================

def archive_old_rows():
    global active_rows
    global csv_file
    global csv_writer

    print(
        "=== CSV ARCHIVE START ===",
        flush=True
    )

    print(
        f"Active rows before archive: {active_rows}",
        flush=True
    )

    print(
        f"Moving oldest rows: {ARCHIVE_BATCH_ROWS}",
        flush=True
    )

    if active_rows < MAX_ACTIVE_ROWS:
        print(
            "Archive not required.",
            flush=True
        )
        return True

    close_csv()

    os.makedirs(
        ARCHIVE_DIR,
        exist_ok=True
    )

    timestamp = time.strftime(
        "%Y%m%d_%H%M%S",
        time.gmtime()
    )

    archive_file = os.path.join(
        ARCHIVE_DIR,
        f"trades_archive_{timestamp}.csv"
    )

    temp_archive = (
        archive_file + ".tmp"
    )

    temp_active = (
        OUTPUT_FILE + ".tmp"
    )

    try:
        archived_count = 0
        remaining_count = 0

        with open(
            OUTPUT_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as source:

            reader = csv.reader(source)

            header = next(reader)

            with open(
                temp_archive,
                "w",
                newline="",
                encoding="utf-8"
            ) as archive_out:

                archive_writer = csv.writer(
                    archive_out
                )

                archive_writer.writerow(
                    header
                )

                with open(
                    temp_active,
                    "w",
                    newline="",
                    encoding="utf-8"
                ) as active_out:

                    active_writer = csv.writer(
                        active_out
                    )

                    active_writer.writerow(
                        header
                    )

                    for row in reader:

                        if (
                            archived_count
                            < ARCHIVE_BATCH_ROWS
                        ):
                            archive_writer.writerow(
                                row
                            )

                            archived_count += 1

                        else:
                            active_writer.writerow(
                                row
                            )

                            remaining_count += 1

                    archive_out.flush()
                    os.fsync(
                        archive_out.fileno()
                    )

                    active_out.flush()
                    os.fsync(
                        active_out.fileno()
                    )

        if archived_count != ARCHIVE_BATCH_ROWS:
            raise RuntimeError(
                "Archive row count mismatch"
            )

        os.replace(
            temp_archive,
            archive_file
        )

        os.replace(
            temp_active,
            OUTPUT_FILE
        )

        active_rows = remaining_count

        print(
            f"Archived rows: {archived_count}",
            flush=True
        )

        print(
            f"Active rows after archive: {active_rows}",
            flush=True
        )

        print(
            f"Archive file: {archive_file}",
            flush=True
        )

        print(
            "=== CSV ARCHIVE COMPLETE ===",
            flush=True
        )

        open_csv()

        return True

    except Exception as e:

        print(
            f"=== CSV ARCHIVE ERROR: {e} ===",
            flush=True
        )

        try:
            if os.path.exists(temp_archive):
                os.remove(temp_archive)
        except Exception:
            pass

        try:
            if os.path.exists(temp_active):
                os.remove(temp_active)
        except Exception:
            pass

        open_csv()

        return False


def ensure_archive_capacity():
    if active_rows >= MAX_ACTIVE_ROWS:
        return archive_old_rows()

    return True


# ============================================================
# GIT
# ============================================================

def run_git(command):
    return subprocess.run(
        command,
        check=True
    )


def prepare_git_checkpoint():
    print(
        "=== PREPARING GIT CHECKPOINT ===",
        flush=True
    )

    flush_csv()

    run_git([
        "git",
        "fetch",
        "origin",
        "main"
    ])

    run_git([
        "git",
        "reset",
        "--soft",
        "origin/main"
    ])

    run_git([
        "git",
        "add",
        OUTPUT_FILE,
        ARCHIVE_DIR
    ])


def commit_if_needed():
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

        return False

    run_git([
        "git",
        "commit",
        "-m",
        "Checkpoint Tabdeal BTC_USDT trades"
    ])

    return True


def push_checkpoint(max_retries=3):

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                f"=== GIT PUSH ATTEMPT {attempt}/{max_retries} ===",
                flush=True
            )

            run_git([
                "git",
                "push",
                "origin",
                "main"
            ])

            print(
                "=== GIT PUSH SUCCESS ===",
                flush=True
            )

            return True

        except Exception as e:

            print(
                f"GIT PUSH ERROR: {e}",
                flush=True
            )

            if attempt >= max_retries:
                print(
                    "=== GIT PUSH FAILED AFTER RETRIES ===",
                    flush=True
                )

                return False

            try:
                prepare_git_checkpoint()

                committed = commit_if_needed()

                if not committed:
                    return True

            except Exception as refresh_error:

                print(
                    f"GIT REFRESH ERROR: {refresh_error}",
                    flush=True
                )

    return False


def git_checkpoint():
    global last_checkpoint_time

    try:

        print(
            "=== GIT CHECKPOINT START ===",
            flush=True
        )

        if csv_file:
            flush_csv()

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

        prepare_git_checkpoint()

        committed = commit_if_needed()

        if not committed:
            last_checkpoint_time = time.time()
            return True

        success = push_checkpoint(
            max_retries=3
        )

        if success:
            last_checkpoint_time = time.time()
            return True

        return False

    except Exception as e:

        print(
            f"=== CHECKPOINT ERROR: {e} ===",
            flush=True
        )

        return False


def maybe_checkpoint():

    if (
        time.time()
        - last_checkpoint_time
        >= CHECKPOINT_SECONDS
    ):

        git_checkpoint()


# ============================================================
# TRADE SAVING
# ============================================================

def save_trade(trade):
    global last_sequence
    global trade_count
    global active_rows

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

    if (
        last_sequence is not None
        and sequence <= last_sequence
    ):
        return

    # Keep active CSV below the maximum.
    if active_rows >= MAX_ACTIVE_ROWS:

        success = ensure_archive_capacity()

        if not success:
            print(
                "ARCHIVE FAILED - TRADE NOT WRITTEN",
                flush=True
            )

            return

    csv_writer.writerow([
        trade.get("symbol"),
        trade.get("price"),
        trade.get("amount"),
        trade.get("side_name"),
        trade.get("updated"),
        sequence
    ])

    flush_csv()

    last_sequence = sequence
    trade_count += 1
    active_rows += 1

    print(
        f"SAVED | "
        f"{trade.get('updated')} | "
        f"{trade.get('side_name')} | "
        f"{trade.get('price')} | "
        f"{trade.get('amount')} | "
        f"seq={sequence}",
        flush=True
    )

    maybe_checkpoint()


# ============================================================
# SIGNALS
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

    if current_ws:

        try:
            current_ws.close()

        except Exception:
            pass


signal.signal(
    signal.SIGINT,
    stop_collector
)

signal.signal(
    signal.SIGTERM,
    stop_collector
)


# ============================================================
# WEBSOCKET
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


def on_error(
    ws,
    error
):

    print(
        f"=== WEBSOCKET ERROR === {error}",
        flush=True
    )


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
# COLLECTION
# ============================================================

def collect():
    global running
    global current_ws

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
        f"Max active rows: {MAX_ACTIVE_ROWS}",
        flush=True
    )

    print(
        f"Archive batch rows: {ARCHIVE_BATCH_ROWS}",
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

            current_ws = ws

            timer = threading.Timer(
                remaining,
                close_websocket,
                args=(ws,)
            )

            timer.daemon = True
            timer.start()

            try:

                ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10
                )

            finally:

                timer.cancel()

                if current_ws is ws:
                    current_ws = None

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

        collect()

    finally:

        if csv_file:
            flush_csv()

        print(
            "=== FINAL GIT CHECKPOINT ===",
            flush=True
        )

        git_checkpoint()

        close_csv()

        print(
            "=== CSV CLOSED SAFELY ===",
            flush=True
        )


if __name__ == "__main__":
    main()
