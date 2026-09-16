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

WS_URL = os.getenv(
    "TABDEAL_WS_URL",
    "wss://api1.tabdeal.org/special_margin/broadcast/"
)

SYMBOL = os.getenv(
    "TABDEAL_SYMBOL",
    "BTC_USDT"
)

OUTPUT_FILE = os.getenv(
    "TRADES_OUTPUT_FILE",
    "data/trades.csv"
)

RECONNECT_DELAY = int(
    os.getenv("RECONNECT_DELAY", "5")
)

# GitHub mode:
# RUN_FOREVER=0
# RUN_SECONDS=5h20m
#
# VPS 24/7 mode:
# RUN_FOREVER=1

RUN_FOREVER = os.getenv(
    "RUN_FOREVER",
    "0"
).lower() in ("1", "true", "yes")

RUN_SECONDS = int(
    os.getenv(
        "RUN_SECONDS",
        str(5 * 60 * 60 + 20 * 60)
    )
)

CHECKPOINT_SECONDS = int(
    os.getenv(
        "CHECKPOINT_SECONDS",
        str(20 * 60)
    )
)

# GitHub = enabled
# VPS = disabled

ENABLE_GIT_CHECKPOINT = os.getenv(
    "ENABLE_GIT_CHECKPOINT",
    "1"
).lower() in ("1", "true", "yes")


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
# SIGNAL HANDLING
# ============================================================

def handle_shutdown(signum, frame):
    """
    Graceful shutdown for SIGTERM / SIGINT.

    GitHub Actions and VPS can both use these signals.
    The websocket is closed so the main loop can finish
    and perform the final checkpoint.
    """

    global running
    global current_ws

    print(
        f"=== SHUTDOWN SIGNAL RECEIVED: {signum} ===",
        flush=True
    )

    running = False

    if current_ws is not None:

        try:
            current_ws.close()
        except Exception:
            pass


signal.signal(
    signal.SIGTERM,
    handle_shutdown
)

signal.signal(
    signal.SIGINT,
    handle_shutdown
)


# ============================================================
# LOAD LAST SEQUENCE
# ============================================================

def load_last_sequence():
    """
    Load the last saved sequence from the active CSV.

    This is independent of GitHub.
    Therefore the same logic works on VPS.
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

    directory = os.path.dirname(
        OUTPUT_FILE
    )

    if directory:

        os.makedirs(
            directory,
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

            os.fsync(
                csv_file.fileno()
            )

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
                f"CSV flush error: {e}",
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


def git_push_with_retry(max_retries=3):

    """
    Push the checkpoint commit.

    If the remote changed meanwhile:
    fetch -> rebase -> push again.

    A Git failure NEVER stops the collector.
    """

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                f"Git push attempt {attempt}/{max_retries}",
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
                f"Git push failed on attempt {attempt}: {e}",
                flush=True
            )

            if attempt >= max_retries:
                break

            try:

                print(
                    "=== FETCHING REMOTE CHANGES ===",
                    flush=True
                )

                run_git([
                    "git",
                    "fetch",
                    "origin",
                    "main"
                ])

                print(
                    "=== REBASING LOCAL CHECKPOINT ===",
                    flush=True
                )

                run_git([
                    "git",
                    "rebase",
                    "origin/main"
                ])

            except subprocess.CalledProcessError as rebase_error:

                print(
                    f"Git rebase failed: {rebase_error}",
                    flush=True
                )

                try:

                    run_git([
                        "git",
                        "rebase",
                        "--abort"
                    ])

                except Exception:
                    pass

                break

            time.sleep(2)

        except Exception as e:

            print(
                f"Unexpected Git push error: {e}",
                flush=True
            )

            break

    print(
        "=== GIT PUSH FAILED - COLLECTOR CONTINUES ===",
        flush=True
    )

    return False


# ============================================================
# GIT CHECKPOINT
# ============================================================

def git_checkpoint():

    global last_checkpoint_time

    if not ENABLE_GIT_CHECKPOINT:

        print(
            "=== GIT CHECKPOINT DISABLED ===",
            flush=True
        )

        last_checkpoint_time = time.time()

        return True

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

        # Make sure the local repository knows the latest remote state.
        try:

            run_git([
                "git",
                "fetch",
                "origin",
                "main"
            ])

        except subprocess.CalledProcessError as e:

            print(
                f"Git fetch warning: {e}",
                flush=True
            )

        # Add only the active data file.
        run_git([
            "git",
            "add",
            OUTPUT_FILE
        ])

        # Check whether there is actually something to commit.
        status = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--quiet"
            ],
            check=False
        )

        if status.returncode == 0:

            print(
                "=== NO NEW DATA TO COMMIT ===",
                flush=True
            )

            last_checkpoint_time = time.time()

            return True

        # Commit checkpoint.
        run_git([
            "git",
            "commit",
            "-m",
            "Checkpoint Tabdeal BTC_USDT trades"
        ])

        # Push with retry/rebase protection.
        success = git_push_with_retry(
            max_retries=3
        )

        last_checkpoint_time = time.time()

        return success

    except subprocess.CalledProcessError as e:

        print(
            f"=== GIT CHECKPOINT ERROR: {e} ===",
            flush=True
        )

        print(
            "Collector will continue.",
            flush=True
        )

        last_checkpoint_time = time.time()

        return False

    except Exception as e:

        print(
            f"=== UNEXPECTED CHECKPOINT ERROR: {e} ===",
            flush=True
        )

        print(
            "Collector will continue.",
            flush=True
        )

        last_checkpoint_time = time.time()

        return False


# ============================================================
# DATA PARSING
# ============================================================

def extract_trade(data):

    """
    Extract a trade from Tabdeal websocket messages.

    Returns:
        (price, amount, side, updated, sequence)
    or
        None
    """

    if not isinstance(data, dict):
        return None

    # --------------------------------------------------------
    # Ignore order events
    # --------------------------------------------------------

    event_type = str(
        data.get("e")
        or data.get("event")
        or data.get("type")
        or ""
    ).lower()

    if "order" in event_type:

        print(
            "ORDER EVENT IGNORED",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # Locate payload
    # --------------------------------------------------------

    payload = data

    for key in (
        "data",
        "result",
        "trade",
        "payload"
    ):

        candidate = data.get(key)

        if isinstance(candidate, dict):

            payload = candidate
            break

    # --------------------------------------------------------
    # Extract fields
    # --------------------------------------------------------

    sequence = (
        payload.get("sequence")
        or payload.get("seq")
        or payload.get("id")
        or data.get("sequence")
        or data.get("seq")
    )

    price = (
        payload.get("price")
        or payload.get("p")
    )

    amount = (
        payload.get("amount")
        or payload.get("qty")
        or payload.get("quantity")
        or payload.get("q")
    )

    side = (
        payload.get("side")
        or payload.get("S")
        or payload.get("direction")
    )

    updated = (
        payload.get("updated")
        or payload.get("timestamp")
        or payload.get("time")
        or payload.get("T")
    )

    if sequence is None:
        return None

    if price is None:
        return None

    if amount is None:
        return None

    if side is None:
        return None

    try:

        sequence = int(sequence)

    except Exception:

        return None

    return (
        price,
        amount,
        side,
        updated,
        sequence
    )


# ============================================================
# SAVE TRADE
# ============================================================

def save_trade(
    price,
    amount,
    side,
    updated,
    sequence
):

    global last_sequence
    global trade_count

    # --------------------------------------------------------
    # Sequence protection
    # --------------------------------------------------------

    if last_sequence is not None:

        if sequence <= last_sequence:

            return

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    csv_writer.writerow([
        SYMBOL,
        price,
        amount,
        side,
        updated,
        sequence
    ])

    flush_csv()

    last_sequence = sequence

    trade_count += 1

    print(
        f"SAVED | {updated} | {side} | "
        f"{price} | {amount} | seq={sequence}",
        flush=True
    )


# ============================================================
# WEBSOCKET CALLBACKS
# ============================================================

def on_message(ws, message):

    global last_checkpoint_time

    if not running:
        return

    try:

        data = json.loads(message)

    except Exception as e:

        print(
            f"JSON ERROR: {e}",
            flush=True
        )

        return

    trade = extract_trade(data)

    if trade is not None:

        save_trade(
            *trade
        )

    # --------------------------------------------------------
    # Periodic checkpoint
    # --------------------------------------------------------

    if (
        time.time()
        - last_checkpoint_time
        >= CHECKPOINT_SECONDS
    ):

        git_checkpoint()


def on_error(ws, error):

    print(
        f"=== WEBSOCKET ERROR: {error} ===",
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


def on_open(ws):

    print(
        "=== CONNECTED ===",
        flush=True
    )


# ============================================================
# MAIN COLLECTOR
# ============================================================

def main():

    global last_sequence
    global current_ws
    global running
    global last_checkpoint_time

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
        f"Run forever: {RUN_FOREVER}",
        flush=True
    )

    print(
        f"Duration: "
        f"{'24/7' if RUN_FOREVER else str(RUN_SECONDS) + ' seconds'}",
        flush=True
    )

    print(
        f"Checkpoint: every {CHECKPOINT_SECONDS} seconds",
        flush=True
    )

    print(
        f"Git checkpoint: {ENABLE_GIT_CHECKPOINT}",
        flush=True
    )

    # --------------------------------------------------------
    # Load sequence BEFORE opening CSV
    # --------------------------------------------------------

    last_sequence = load_last_sequence()

    print(
        f"Last saved sequence: {last_sequence}",
        flush=True
    )

    # --------------------------------------------------------
    # Open CSV
    # --------------------------------------------------------

    open_csv()

    start_time = time.time()

    last_checkpoint_time = time.time()

    try:

        while running:

            # ------------------------------------------------
            # Duration check
            # ------------------------------------------------

            if not RUN_FOREVER:

                elapsed = (
                    time.time()
                    - start_time
                )

                if elapsed >= RUN_SECONDS:

                    print(
                        "=== RUN TIME COMPLETED ===",
                        flush=True
                    )

                    break

            # ------------------------------------------------
            # WebSocket connection
            # ------------------------------------------------

            print(
                f"=== CONNECTING {WS_URL} ===",
                flush=True
            )

            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            current_ws = ws

            try:

                ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10
                )

            except Exception as e:

                print(
                    f"WebSocket run error: {e}",
                    flush=True
                )

            finally:

                current_ws = None

            # ------------------------------------------------
            # Shutdown requested
            # ------------------------------------------------

            if not running:
                break

            # ------------------------------------------------
            # Runtime check
            # ------------------------------------------------

            if not RUN_FOREVER:

                elapsed = (
                    time.time()
                    - start_time
                )

                if elapsed >= RUN_SECONDS:
                    break

            # ------------------------------------------------
            # Reconnect
            # ------------------------------------------------

            print(
                f"=== RECONNECTING IN "
                f"{RECONNECT_DELAY} SECONDS ===",
                flush=True
            )

            for _ in range(RECONNECT_DELAY):

                if not running:
                    break

                time.sleep(1)

    except KeyboardInterrupt:

        print(
            "=== KEYBOARD INTERRUPT ===",
            flush=True
        )

        running = False

    except Exception as e:

        print(
            f"=== COLLECTOR ERROR: {e} ===",
            flush=True
        )

    finally:

        print(
            "=== FINALIZING COLLECTOR ===",
            flush=True
        )

        # ----------------------------------------------------
        # Final CSV flush
        # ----------------------------------------------------

        flush_csv()

        # ----------------------------------------------------
        # Final Git checkpoint
        # ----------------------------------------------------

        if ENABLE_GIT_CHECKPOINT:

            print(
                "=== FINAL GIT CHECKPOINT ===",
                flush=True
            )

            git_checkpoint()

        else:

            print(
                "=== FINAL GIT CHECKPOINT DISABLED ===",
                flush=True
            )

        # ----------------------------------------------------
        # Close websocket
        # ----------------------------------------------------

        if current_ws is not None:

            try:
                current_ws.close()
            except Exception:
                pass

        # ----------------------------------------------------
        # Close CSV
        # ----------------------------------------------------

        close_csv()

        print(
            "=== COLLECTOR STOPPED CLEANLY ===",
            flush=True
        )

        print(
            f"Trades collected this run: {trade_count}",
            flush=True
        )

        print(
            f"Last sequence: {last_sequence}",
            flush=True
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
