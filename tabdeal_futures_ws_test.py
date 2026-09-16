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

# Current GitHub mode:
# 5 hours 20 minutes
#
# For VPS 24/7 mode:
# set RUN_FOREVER=1
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

# Checkpoint interval
CHECKPOINT_SECONDS = int(
    os.getenv(
        "CHECKPOINT_SECONDS",
        str(20 * 60)
    )
)

# Git checkpoint:
# GitHub Actions = enabled
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
# LOAD LAST SEQUENCE
# ============================================================

def load_last_sequence():
    """
    Load the last saved sequence from the active CSV.

    This is intentionally independent of GitHub.
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


# ============================================================
# GIT CHECKPOINT
# ============================================================

def run_git(command):

    return subprocess.run(
        command,
        check=True
    )


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

        if csv_file:

            csv_file.flush()

            try:
                os.fsync(
                    csv_file.fileno()
                )
            except Exception:
                pass

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

        #
