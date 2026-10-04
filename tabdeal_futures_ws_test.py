import csv
import hashlib
import json
import os
import signal
import subprocess
import threading
import time

import websocket


# ============================================================
# CONFIGURATION
#
# Application: Hes Trade Agent
# Owner: Seyed Hesameddin Beheshti Shirazi
# ============================================================

WS_URL = "wss://api1.tabdeal.org/special_margin/broadcast/"
SYMBOL = "BTC_USDT"

OUTPUT_FILE = "data/trades.csv"
ARCHIVE_DIR = "data/archive"

RECONNECT_DELAY = 5

# Default collection window.
#
# Backward compatibility:
# - GitHub Actions keeps the historical 5h 20m default.
# - VPS systemd sets COLLECTOR_RUN_SECONDS=0 for true continuous mode.
DEFAULT_RUN_SECONDS = 5 * 60 * 60 + 20 * 60


def get_run_seconds():
    """
    Return the validated collection window from the runtime
    environment.

    Values:
        > 0  = finite collection window in seconds
        0    = continuous mode (no collection timer)

    Example:
        COLLECTOR_RUN_SECONDS=0
    """

    raw_value = os.getenv("COLLECTOR_RUN_SECONDS")

    if raw_value is None:
        return DEFAULT_RUN_SECONDS

    try:
        run_seconds = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "COLLECTOR_RUN_SECONDS must be a positive integer"
        ) from exc

    if run_seconds < 0:
        raise ValueError(
            "COLLECTOR_RUN_SECONDS must be a non-negative integer"
        )

    return run_seconds


RUN_SECONDS = get_run_seconds()

# Git checkpoint every 20 minutes
CHECKPOINT_SECONDS = 20 * 60

# Active CSV size management
MAX_ACTIVE_ROWS = 150000
ARCHIVE_BATCH_ROWS = 50000
ARCHIVE_TXN_MARKER = os.path.join("data", ".archive_rotation.json")


# ============================================================
# RUNTIME STATE
# ============================================================

running = True
last_sequence = None
trade_count = 0

# Immutable collector-session base. A checkpoint may only publish data
# derived from the exact main snapshot used at startup.
startup_base_sha = None

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


def get_max_sequence_from_file(file_path):
    max_sequence = None

    if not os.path.exists(file_path):
        return None

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
            newline=""
        ) as f:
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
        print(
            f"Error reading sequence from {file_path}: {e}",
            flush=True
        )

    return max_sequence


def get_last_physical_sequence(file_path):
    last_sequence = None

    if not os.path.exists(file_path):
        return None

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
            newline=""
        ) as f:
            reader = csv.DictReader(f)

            for row in reader:
                last_sequence = row.get("sequence")

    except Exception as e:
        print(
            f"Error reading physical last row from {file_path}: {e}",
            flush=True
        )

    if last_sequence:
        try:
            return int(last_sequence)
        except (ValueError, TypeError):
            return None

    return None


def synchronize_startup_data_state():
    """Synchronize collector data files to a verified origin/main snapshot."""
    global startup_base_sha

    print("=== STARTUP DATA STATE SYNC START ===", flush=True)

    recover_archive_rotation()

    run_git(["git", "fetch", "origin", "main"])

    remote_sha = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", OUTPUT_FILE, ARCHIVE_DIR],
        check=True,
        capture_output=True,
        text=True,
    )

    local_data_modified = bool(status.stdout.strip())

    if local_data_modified:
        # Handoff-safe mode: never restore an older origin/main snapshot
        # over newer append-only data already persisted on the VPS.
        print(
            "=== LOCAL HANDOFF DATA DETECTED: PRESERVING VPS DATA ===",
            flush=True,
        )
        print(
            status.stdout.strip(),
            flush=True,
        )
    else:
        run_git([
            "git", "restore", "--source=origin/main", "--worktree",
            "--", OUTPUT_FILE, ARCHIVE_DIR
        ])

        verify = subprocess.run(
            ["git", "diff", "--quiet", remote_sha, "--", OUTPUT_FILE, ARCHIVE_DIR]
        )
        if verify.returncode != 0:
            print(
                "Startup data sync verification mismatch; re-applying remote snapshot.",
                flush=True,
            )
            run_git([
                "git", "restore", "--source=origin/main", "--staged", "--worktree",
                "--", OUTPUT_FILE, ARCHIVE_DIR
            ])
            verify_retry = subprocess.run(
                ["git", "diff", "--quiet", remote_sha, "--", OUTPUT_FILE, ARCHIVE_DIR]
            )
            if verify_retry.returncode != 0:
                diagnostic = subprocess.run(
                    ["git", "diff", "--stat", remote_sha, "--", OUTPUT_FILE, ARCHIVE_DIR],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                print(
                    "Startup data sync verification mismatch after retry:\\n"
                    + (diagnostic.stdout or diagnostic.stderr),
                    flush=True,
                )
                raise RuntimeError("Startup data sync verification failed after retry.")

    run_git(["git", "fetch", "origin", "main"])
    latest_remote_sha = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if latest_remote_sha != remote_sha:
        raise RuntimeError(
            "Refusing startup data sync: origin/main advanced during synchronization."
        )

    run_git(["git", "reset", "--mixed", remote_sha])

    startup_base_sha = remote_sha

    print(
        f"=== STARTUP BASE SHA: {startup_base_sha} ===",
        flush=True
    )
    print("=== STARTUP DATA STATE SYNC COMPLETE ===", flush=True)


def load_global_last_sequence():
    print(
        "=== SEQUENCE RECOVERY START ===",
        flush=True
    )

    active_max = get_max_sequence_from_file(
        OUTPUT_FILE
    )

    active_last_physical = get_last_physical_sequence(
        OUTPUT_FILE
    )

    print(
        f"Active last physical sequence: {active_last_physical}",
        flush=True
    )

    print(
        f"Active MAX sequence: {active_max}",
        flush=True
    )

    archive_max = None

    if os.path.isdir(ARCHIVE_DIR):
        for filename in os.listdir(ARCHIVE_DIR):
            if not filename.lower().endswith(".csv"):
                continue

            file_path = os.path.join(
                ARCHIVE_DIR,
                filename
            )

            file_max = get_max_sequence_from_file(
                file_path
            )

            if file_max is None:
                continue

            if archive_max is None or file_max > archive_max:
                archive_max = file_max

    print(
        f"Archive MAX sequence: {archive_max}",
        flush=True
    )

    sequences = []

    if active_max is not None:
        sequences.append(active_max)

    if archive_max is not None:
        sequences.append(archive_max)

    global_max = max(sequences) if sequences else None

    print(
        f"GLOBAL MAX sequence: {global_max}",
        flush=True
    )

    if (
        active_last_physical is not None
        and active_max is not None
        and active_last_physical != active_max
    ):
        print(
            "WARNING: CSV physical order is not chronological.",
            flush=True
        )

    if global_max is None:
        print(
            "No valid sequence found. Starting without sequence recovery.",
            flush=True
        )
    else:
        print(
            f"Using GLOBAL MAX sequence: {global_max}",
            flush=True
        )

    print(
        "=== SEQUENCE RECOVERY COMPLETE ===",
        flush=True
    )

    return global_max


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


def _sha256_file(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_archive_transaction(marker):
    temp_marker = ARCHIVE_TXN_MARKER + ".tmp"
    with open(temp_marker, "w", encoding="utf-8") as f:
        json.dump(marker, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_marker, ARCHIVE_TXN_MARKER)


def _remove_archive_transaction_marker():
    for path in (ARCHIVE_TXN_MARKER, ARCHIVE_TXN_MARKER + ".tmp"):
        if os.path.exists(path):
            os.remove(path)


def recover_archive_rotation():
    """Recover an interrupted archive rotation deterministically after a crash."""
    if not os.path.exists(ARCHIVE_TXN_MARKER):
        return
    with open(ARCHIVE_TXN_MARKER, "r", encoding="utf-8") as f:
        marker = json.load(f)
    phase = marker.get("phase")
    archive_file = marker["archive_file"]
    temp_archive = marker["temp_archive"]
    temp_active = marker["temp_active"]
    old_active_sha256 = marker["old_active_sha256"]
    new_active_sha256 = marker["new_active_sha256"]
    archive_sha256 = marker["archive_sha256"]
    if phase == "prepared":
        # A crash can occur after archive replacement but before the marker
        # advances to archive_replaced. If the archive is present, validate
        # it and continue recovery using the same deterministic state machine.
        if os.path.exists(archive_file):
            if _sha256_file(archive_file) != archive_sha256:
                raise RuntimeError("Prepared archive transaction checksum mismatch.")
            phase = "archive_replaced"
        else:
            for path in (temp_archive, temp_active):
                if os.path.exists(path):
                    os.remove(path)
            _remove_archive_transaction_marker()
            return
    if phase != "archive_replaced":
        raise RuntimeError(f"Unknown archive transaction phase: {phase!r}")
    if not os.path.exists(archive_file):
        raise RuntimeError("Archive transaction marker exists but archive is missing.")
    if _sha256_file(archive_file) != archive_sha256:
        raise RuntimeError("Archive transaction recovery checksum mismatch.")
    if not os.path.exists(OUTPUT_FILE):
        raise RuntimeError("Archive transaction recovery: active file is missing.")
    active_sha256 = _sha256_file(OUTPUT_FILE)
    if active_sha256 == old_active_sha256:
        os.remove(archive_file)
        if os.path.exists(temp_active):
            os.remove(temp_active)
        _remove_archive_transaction_marker()
        return
    if active_sha256 == new_active_sha256:
        if os.path.exists(temp_active):
            os.remove(temp_active)
        _remove_archive_transaction_marker()
        return
    raise RuntimeError("Archive transaction recovery found an unknown active-file state; manual recovery required.")


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
        f"trades_archive_{timestamp}_{time.time_ns()}.csv"
    )

    # Archive names must be collision-safe. A collector can complete two
    # rotations within the same UTC second; reusing a second-resolution name
    # would replace an older archive and silently destroy raw data.
    while os.path.exists(archive_file):
        archive_file = os.path.join(
            ARCHIVE_DIR,
            f"trades_archive_{timestamp}_{time.time_ns()}.csv"
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

        marker = {
            "phase": "prepared",
            "archive_file": archive_file,
            "temp_archive": temp_archive,
            "temp_active": temp_active,
            "old_active_sha256": _sha256_file(OUTPUT_FILE),
            "new_active_sha256": _sha256_file(temp_active),
            "archive_sha256": _sha256_file(temp_archive),
        }
        _write_archive_transaction(marker)

        os.replace(
            temp_archive,
            archive_file
        )

        marker["phase"] = "archive_replaced"
        _write_archive_transaction(marker)

        try:
            os.replace(
                temp_active,
                OUTPUT_FILE
            )
        except Exception:
            # Treat archive + active replacement as one logical transaction.
            # If the active swap fails after the archive became visible,
            # remove that newly-created archive so a retry cannot duplicate
            # the same rows or leave a split-brain data state.
            try:
                if os.path.exists(archive_file):
                    os.remove(archive_file)
            except Exception as rollback_error:
                raise RuntimeError(
                    "Archive rotation rollback failed; manual recovery required."
                ) from rollback_error
            raise

        # Active replacement is the commit point. Keep the marker in
        # archive_replaced until cleanup completes so a crash before marker
        # removal remains recoverable and idempotent.
        _remove_archive_transaction_marker()

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

    # Checkpoint preparation MUST NOT reset the working tree.
    # A mixed reset can move HEAD/index to a newer origin/main while
    # leaving a stale data/trades.csv in place. Staging that stale file
    # could overwrite newer persisted trades.
    run_git([
        "git",
        "add",
        OUTPUT_FILE,
        ARCHIVE_DIR
    ])


def assert_remote_main_unchanged():
    """Fail closed if origin/main moved since this collector started."""
    if startup_base_sha is None:
        raise RuntimeError("Collector startup base SHA is not initialized.")

    run_git([
        "git",
        "fetch",
        "origin",
        "main"
    ])

    current_remote_sha = subprocess.run(
        [
            "git",
            "rev-parse",
            "origin/main"
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if current_remote_sha != startup_base_sha:
        raise RuntimeError(
            "Refusing checkpoint: origin/main advanced since collector startup "
            f"(base={startup_base_sha}, current={current_remote_sha})."
        )

    return current_remote_sha


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
    """
    Push exactly one collector commit.

    A failed push is fail-closed. We deliberately do NOT fetch/reset/re-stage
    against a newer main because that could mix a stale collector snapshot
    with newer persisted data.
    """
    if max_retries != 1:
        print(
            "Checkpoint push retries are disabled for data safety.",
            flush=True
        )

    try:
        print(
            "=== GIT PUSH ATTEMPT 1/1 ===",
            flush=True
        )

        assert_remote_main_unchanged()

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
        print(
            "=== GIT PUSH FAILED CLOSED: NO RETRY / NO RESET / NO OVERWRITE ===",
            flush=True
        )
        return False


def git_checkpoint():
    global last_checkpoint_time
    global startup_base_sha

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

        assert_remote_main_unchanged()

        prepare_git_checkpoint()

        committed = commit_if_needed()

        if not committed:
            last_checkpoint_time = time.time()
            return True

        success = push_checkpoint(
            max_retries=1
        )

        if success:
            startup_base_sha = subprocess.run(
                [
                    "git",
                    "rev-parse",
                    "HEAD"
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
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

    global last_checkpoint_time

    if (
        time.time()
        - last_checkpoint_time
        >= CHECKPOINT_SECONDS
    ):

        success = git_checkpoint()

        # A failed checkpoint must not turn the trade stream into a
        # checkpoint loop. Keep the collector live, but back off to the
        # normal 20-minute cadence and retry on the next interval.
        if not success:
            last_checkpoint_time = time.time()


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
        "=== HES TRADE AGENT | TABDEAL FUTURES COLLECTOR ===",
        flush=True
    )

    print(
        "Owner: Seyed Hesameddin Beheshti Shirazi",
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

    if RUN_SECONDS == 0:
        print(
            "Duration: CONTINUOUS (24/7)",
            flush=True
        )
    else:
        print(
            f"Duration: {RUN_SECONDS // 3600}h "
            f"{(RUN_SECONDS % 3600) // 60}m",
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

        if RUN_SECONDS > 0 and elapsed >= RUN_SECONDS:

            print(
                "=== COLLECTION TIME COMPLETE ===",
                flush=True
            )

            break

        remaining = (
            RUN_SECONDS - elapsed
            if RUN_SECONDS > 0
            else None
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

            timer = None

            if remaining is not None:
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

                if timer is not None:
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

        if RUN_SECONDS > 0 and elapsed >= RUN_SECONDS:

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

            if RUN_SECONDS == 0:
                sleep_time = RECONNECT_DELAY
            else:
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

    synchronize_startup_data_state()

    last_sequence = (
        load_global_last_sequence()
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

        checkpoint_ok = git_checkpoint()

        close_csv()

        print(
            "=== CSV CLOSED SAFELY ===",
            flush=True
        )

        if not checkpoint_ok:
            raise RuntimeError(
                "Final Git checkpoint failed; collected data may not be persisted to origin/main."
            )


if __name__ == "__main__":
    main()
