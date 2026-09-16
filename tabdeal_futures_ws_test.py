import csv
import json
import os
import signal
import subprocess
import threading
import time

import websocket


# ============================================================
# CONFIGURATION
# ============================================================

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"
OUTPUT_FILE = "data/trades.csv"

RECONNECT_DELAY = 5

# EXACT COLLECTION TIME: 5 hours 20 minutes
RUN_SECONDS = 5 * 60 * 60 + 20 * 60

# Git checkpoint every 20 minutes
CHECKPOINT_SECONDS = 20 * 60


# ============================================================
# RUNTIME STATE
# ============================================================

running = True
last_sequence = None
trade_count = 0

csv_file = None
csv_writer = None

current_ws = None

last_checkpoint_time = time.time()


# ============================================================
# LOAD LAST SEQUENCE
# ============================================================

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

                return int(
                    last_row["sequence"]
                )

    except Exception as e:

        print(
            f"Could not read last sequence: {e}",
            flush=True
        )

    return None


# ============================================================
# CSV
# ============================================================

def open_csv():

    global csv_file
    global csv_writer

    file_exists = os.path.exists(
        OUTPUT_FILE
    )

    directory = os.path.dirname(
        OUTPUT_FILE
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True
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

        csv_file.flush()

        try:
            os.fsync(
                csv_file.fileno()
            )
        except Exception:
            pass


def close_csv():

    global csv_file

    if csv_file:

        try:

            csv_file.flush()

            try:
                os.fsync(
                    csv_file.fileno()
                )
            except Exception:
                pass

            csv_file.close()

        except Exception:
            pass

        csv_file = None


def flush_csv():

    if csv_file:

        try:

            csv_file.flush()

            try:
                os.fsync(
                    csv_file.fileno()
                )
            except Exception:
                pass

        except Exception as e:

            print(
                f"CSV FLUSH ERROR: {e}",
                flush=True
            )


# ============================================================
# GIT
# ============================================================

def run_git(command):

    return subprocess.run(
        command,
        check=True
    )


def prepare_git_checkpoint():

    """
    Prepare the local repository for a checkpoint.

    The repository is synchronized with origin/main
    before staging the latest CSV.
    """

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
        OUTPUT_FILE
    ])


def commit_if_needed():

    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--quiet"
        ],
        check=False
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

    """
    Push the current checkpoint.

    If another remote change appears, refresh origin/main,
    rebuild the checkpoint commit and retry.

    Git failure does NOT stop the collector.
    """

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                f"=== GIT PUSH ATTEMPT "
                f"{attempt}/{max_retries} ===",
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

        except subprocess.CalledProcessError as e:

            print(
                f"=== GIT PUSH FAILED "
                f"ATTEMPT {attempt}: {e} ===",
                flush=True
            )

            if attempt >= max_retries:
                break

            try:

                print(
                    "=== REFRESHING REMOTE STATE "
                    "FOR RETRY ===",
                    flush=True
                )

                prepare_git_checkpoint()

                if not commit_if_needed():

                    print(
                        "=== NOTHING TO PUSH AFTER RETRY PREPARATION ===",
                        flush=True
                    )

                    return True

            except Exception as retry_error:

                print(
                    f"=== GIT RETRY PREPARATION ERROR: "
                    f"{retry_error} ===",
                    flush=True
                )

                break

            time.sleep(2)

        except Exception as e:

            print(
                f"=== UNEXPECTED GIT PUSH ERROR: {e} ===",
                flush=True
            )

            break

    print(
        "=== GIT PUSH FAILED - "
        "COLLECTOR WILL CONTINUE ===",
        flush=True
    )

    return False


# ============================================================
# GIT CHECKPOINT
# ============================================================

def git_checkpoint():

    global last_checkpoint_time

    try:

        flush_csv()

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

        prepare_git_checkpoint()

        has_commit = commit_if_needed()

        if not has_commit:

            last_checkpoint_time = time.time()

            return True

        success = push_checkpoint(
            max_retries=3
        )

        if success:

            print(
                "=== GIT CHECKPOINT COMPLETE ===",
                flush=True
            )

        else:

            print(
                "=== GIT CHECKPOINT FAILED "
                "BUT COLLECTOR CONTINUES ===",
                flush=True
            )

        last_checkpoint_time = time.time()

        return success

    except Exception as e:

        print(
            f"=== CHECKPOINT ERROR: {e} ===",
            flush=True
        )

        print(
            "=== COLLECTOR WILL CONTINUE ===",
            flush=True
        )

        last_checkpoint_time = time.time()

        return False


# ============================================================
# PERIODIC CHECKPOINT
# ============================================================

def maybe_checkpoint():

    if (
        time.time()
        - last_checkpoint_time
        >= CHECKPOINT_SECONDS
    ):

        git_checkpoint()


# ============================================================
# SAVE TRADE
# ============================================================

def save_trade(trade):

    global last_sequence
    global trade_count

    sequence_raw = trade.get(
        "sequence"
    )

    if sequence_raw is None:
        return

    try:

        sequence = int(
            sequence_raw
        )

    except (ValueError, TypeError):

        return

    if (
        last_sequence is not None
        and sequence <= last_sequence
    ):

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
# SIGNAL HANDLING
# ============================================================

def stop_collector(
    signum=None,
    frame=None
):

    global running
    global current_ws

    print(
        "\n=== STOP SIGNAL RECEIVED ===",
        flush=True
    )

    running = False

    if current_ws is not None:

        try:

            print(
                "=== CLOSING WEBSOCKET FOR CLEAN SHUTDOWN ===",
                flush=True
            )

            current_ws.close()

        except Exception as e:

            print(
                f"WEBSOCKET CLOSE ERROR: {e}",
                flush=True
            )


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


def on_message(ws, message):

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


def on_error(ws, error):

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
            "=== COLLECTION TIMER: "
            "CLOSING WEBSOCKET ===",
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

        collect()

    finally:

        # ----------------------------------------------------
        # Always flush/close CSV safely
        # ----------------------------------------------------

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


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
