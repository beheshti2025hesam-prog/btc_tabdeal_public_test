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

# EXACT COLLECTION TIME: 5h20m
RUN_SECONDS = 5 * 60 * 60 + 20 * 60

CHECKPOINT_SECONDS = 20 * 60

MAX_ACTIVE_ROWS = 150000
ARCHIVE_BATCH_ROWS = 50000


stop_event = threading.Event()


def get_max_sequence_from_file(file_path):
    """
    Return the maximum valid sequence found anywhere in the CSV.

    IMPORTANT:
    Sequence recovery must NOT depend on physical CSV row order.
    """
    max_sequence = None

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                sequence = row.get("sequence")

                if not sequence:
                    continue

                try:
                    sequence = int(sequence)
                except (ValueError, TypeError):
                    continue

                if max_sequence is None or sequence > max_sequence:
                    max_sequence = sequence

    except Exception as e:
        print(f"Error reading sequence from {file_path}: {e}")

    return max_sequence


def get_last_physical_sequence(file_path):
    """
    Diagnostic only.

    Returns the sequence from the physically last CSV row.
    This value is NOT used for sequence recovery.
    """
    last_sequence = None

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                last_sequence = row.get("sequence")

    except Exception as e:
        print(f"Error reading physical last row from {file_path}: {e}")

    if last_sequence:
        try:
            return int(last_sequence)
        except (ValueError, TypeError):
            return None

    return None


def load_global_last_sequence():
    """
    Recover the latest known sequence from:

    1. Active CSV
    2. All CSV files in Permanent Archive

    The GLOBAL MAX sequence is used as the recovery point.
    Physical CSV row order is intentionally ignored.
    """

    print("=== SEQUENCE RECOVERY START ===")

    # ---------------------------------------------------------
    # Active CSV
    # ---------------------------------------------------------
    active_max = get_max_sequence_from_file(OUTPUT_FILE)
    active_last_physical = get_last_physical_sequence(OUTPUT_FILE)

    print(f"Active last physical sequence: {active_last_physical}")
    print(f"Active MAX sequence: {active_max}")

    # ---------------------------------------------------------
    # Archive CSVs
    # ---------------------------------------------------------
    archive_max = None

    if os.path.isdir(ARCHIVE_DIR):

        for filename in os.listdir(ARCHIVE_DIR):

            if not filename.lower().endswith(".csv"):
                continue

            file_path = os.path.join(ARCHIVE_DIR, filename)

            file_max = get_max_sequence_from_file(file_path)

            if file_max is None:
                continue

            if archive_max is None or file_max > archive_max:
                archive_max = file_max

    print(f"Archive MAX sequence: {archive_max}")

    # ---------------------------------------------------------
    # Global MAX
    # ---------------------------------------------------------
    sequences = []

    if active_max is not None:
        sequences.append(active_max)

    if archive_max is not None:
        sequences.append(archive_max)

    if not sequences:
        global_max = None
    else:
        global_max = max(sequences)

    print(f"GLOBAL MAX sequence: {global_max}")

    # ---------------------------------------------------------
    # Diagnostic warning
    # ---------------------------------------------------------
    if (
        active_last_physical is not None
        and active_max is not None
        and active_last_physical != active_max
    ):
        print("WARNING: CSV physical order is not chronological.")

    # ---------------------------------------------------------
    # Final result
    # ---------------------------------------------------------
    if global_max is None:
        print("No valid sequence found. Starting without sequence recovery.")
    else:
        print(f"Using GLOBAL MAX sequence: {global_max}")

    print("=== SEQUENCE RECOVERY COMPLETE ===")

    return global_max


def load_existing_rows_count():
    if not os.path.exists(OUTPUT_FILE):
        return 0

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)

            # Header
            next(reader, None)

            return sum(1 for _ in reader)

    except Exception as e:
        print(f"Error counting active rows: {e}")
        return 0


def archive_old_rows():
    """
    Move the first physical ARCHIVE_BATCH_ROWS rows from Active
    into a permanent archive when Active exceeds MAX_ACTIVE_ROWS.

    NOTE:
    This function intentionally remains unchanged for the current
    Global MAX validation phase.

    Historical analysis must later be timestamp-aware in Data Engine.
    """

    if not os.path.exists(OUTPUT_FILE):
        return

    row_count = load_existing_rows_count()

    if row_count <= MAX_ACTIVE_ROWS:
        return

    print(f"Active CSV rows before archive: {row_count}")
    print("Active CSV limit reached. Moving oldest rows...")

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())

    archive_file = os.path.join(
        ARCHIVE_DIR,
        f"trades_archive_{timestamp}.csv"
    )

    rows_to_archive = ARCHIVE_BATCH_ROWS

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as source:

            reader = csv.reader(source)

            header = next(reader, None)

            rows = []

            for row in reader:
                rows.append(row)

        if not header:
            return

        archive_rows = rows[:rows_to_archive]
        remaining_rows = rows[rows_to_archive:]

        if not archive_rows:
            return

        # -----------------------------------------------------
        # Write permanent archive
        # -----------------------------------------------------
        with open(
            archive_file,
            "w",
            encoding="utf-8",
            newline=""
        ) as archive:

            writer = csv.writer(archive)

            writer.writerow(header)
            writer.writerows(archive_rows)

        # -----------------------------------------------------
        # Rewrite active CSV
        # -----------------------------------------------------
        temp_file = OUTPUT_FILE + ".tmp"

        with open(
            temp_file,
            "w",
            encoding="utf-8",
            newline=""
        ) as active:

            writer = csv.writer(active)

            writer.writerow(header)
            writer.writerows(remaining_rows)

            active.flush()
            os.fsync(active.fileno())

        os.replace(temp_file, OUTPUT_FILE)

        print(
            f"Archived {len(archive_rows)} rows to "
            f"{archive_file}"
        )

        print(
            f"Active CSV rows after archive: "
            f"{len(remaining_rows)}"
        )

    except Exception as e:
        print(f"Archive error: {e}")


def git_checkpoint():

    try:

        print("=== GIT CHECKPOINT START ===")

        subprocess.run(
            ["git", "fetch", "origin", "main"],
            check=True
        )

        subprocess.run(
            ["git", "reset", "--soft", "origin/main"],
            check=True
        )

        subprocess.run(
            [
                "git",
                "add",
                "data/trades.csv",
                "data/archive"
            ],
            check=True
        )

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"]
        )

        if result.returncode == 0:
            print("No changes to commit.")
            return True

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Checkpoint Tabdeal BTC_USDT trades"
            ],
            check=True
        )

        for attempt in range(1, 4):

            try:

                print(f"Push attempt {attempt}/3")

                subprocess.run(
                    [
                        "git",
                        "push",
                        "origin",
                        "HEAD:main"
                    ],
                    check=True
                )

                print("Git checkpoint push succeeded.")
                return True

            except subprocess.CalledProcessError:

                print(
                    f"Push attempt {attempt} failed."
                )

                if attempt < 3:

                    subprocess.run(
                        ["git", "fetch", "origin", "main"],
                        check=False
                    )

                    subprocess.run(
                        ["git", "reset", "--soft", "origin/main"],
                        check=False
                    )

                    subprocess.run(
                        [
                            "git",
                            "add",
                            "data/trades.csv",
                            "data/archive"
                        ],
                        check=False
                    )

                    result = subprocess.run(
                        ["git", "diff", "--cached", "--quiet"]
                    )

                    if result.returncode != 0:

                        subprocess.run(
                            [
                                "git",
                                "commit",
                                "-m",
                                "Checkpoint Tabdeal BTC_USDT trades"
                            ],
                            check=False
                        )

                    time.sleep(2)

        print("Git checkpoint push failed after 3 attempts.")
        return False

    except Exception as e:

        print(f"Git checkpoint error: {e}")
        return False

    finally:

        print("=== GIT CHECKPOINT END ===")


def checkpoint_worker():

    while not stop_event.wait(CHECKPOINT_SECONDS):

        try:

            archive_old_rows()

            git_checkpoint()

        except Exception as e:

            print(f"Checkpoint worker error: {e}")


def safe_close(ws):

    try:
        if ws:
            ws.close()
    except Exception:
        pass


def handle_signal(signum, frame):

    print(f"Received signal {signum}. Stopping...")

    stop_event.set()


def main():

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # =========================================================
    # GLOBAL SEQUENCE RECOVERY
    # =========================================================

    last_sequence = load_global_last_sequence()

    if last_sequence is None:
        print("No previous sequence found.")
    else:
        print(f"Last recovered GLOBAL sequence: {last_sequence}")

    active_rows = load_existing_rows_count()

    print(f"Active CSV rows: {active_rows}")

    # =========================================================
    # Checkpoint thread
    # =========================================================

    checkpoint_thread = threading.Thread(
        target=checkpoint_worker,
        daemon=True
    )

    checkpoint_thread.start()

    start_time = time.time()

    while not stop_event.is_set():

        elapsed = time.time() - start_time

        if elapsed >= RUN_SECONDS:
            print("Exact collection time reached.")
            break

        ws = None

        try:

            print("Connecting to Tabdeal WebSocket...")

            ws = websocket.create_connection(
                WS_URL,
                ping_interval=20,
                ping_timeout=10
            )

            print("WebSocket connected.")

            while not stop_event.is_set():

                elapsed = time.time() - start_time

                if elapsed >= RUN_SECONDS:
                    break

                try:

                    message = ws.recv()

                    if not message:
                        continue

                    data = json.loads(message)

                    # -------------------------------------------------
                    # Normalize possible message structures
                    # -------------------------------------------------

                    trade = None

                    if isinstance(data, dict):

                        if "data" in data and isinstance(
                            data["data"], dict
                        ):
                            trade = data["data"]

                        elif "trade" in data and isinstance(
                            data["trade"], dict
                        ):
                            trade = data["trade"]

                        else:
                            trade = data

                    if not isinstance(trade, dict):
                        continue

                    symbol = trade.get("symbol")

                    if symbol and symbol != SYMBOL:
                        continue

                    sequence = trade.get("sequence")

                    if sequence is None:
                        continue

                    try:
                        sequence = int(sequence)
                    except (ValueError, TypeError):
                        continue

                    # -------------------------------------------------
                    # Sequence filtering
                    # -------------------------------------------------

                    if (
                        last_sequence is not None
                        and sequence <= last_sequence
                    ):
                        continue

                    price = trade.get("price")
                    amount = trade.get("amount")
                    side = trade.get("side")
                    updated = trade.get("updated")

                    if (
                        price is None
                        or amount is None
                        or side is None
                        or updated is None
                    ):
                        continue

                    row = [
                        SYMBOL,
                        price,
                        amount,
                        side,
                        updated,
                        sequence
                    ]

                    file_exists = os.path.exists(OUTPUT_FILE)

                    with open(
                        OUTPUT_FILE,
                        "a",
                        encoding="utf-8",
                        newline=""
                    ) as f:

                        writer = csv.writer(f)

                        if not file_exists:
                            writer.writerow(
                                [
                                    "symbol",
                                    "price",
                                    "amount",
                                    "side",
                                    "updated",
                                    "sequence"
                                ]
                            )

                        writer.writerow(row)

                        f.flush()
                        os.fsync(f.fileno())

                    last_sequence = sequence

                    print(
                        f"{updated} | "
                        f"{SYMBOL} | "
                        f"{price} | "
                        f"{amount} | "
                        f"{side} | "
                        f"{sequence}"
                    )

                except websocket.WebSocketTimeoutException:

                    continue

                except websocket.WebSocketConnectionClosedException:

                    print(
                        "WebSocket connection closed."
                    )

                    break

                except json.JSONDecodeError:

                    continue

                except Exception as e:

                    print(
                        f"Message processing error: {e}"
                    )

                    continue

        except Exception as e:

            print(
                f"WebSocket connection error: {e}"
            )

        finally:

            safe_close(ws)

        if not stop_event.is_set():

            print(
                f"Reconnecting in "
                f"{RECONNECT_DELAY} seconds..."
            )

            stop_event.wait(RECONNECT_DELAY)

    # =========================================================
    # Final checkpoint
    # =========================================================

    print("Collection finished.")

    stop_event.set()

    checkpoint_thread.join(timeout=10)

    try:

        archive_old_rows()

        git_checkpoint()

    except Exception as e:

        print(
            f"Final checkpoint error: {e}"
        )

    print("Collector finished successfully.")


if __name__ == "__main__":
    main()
