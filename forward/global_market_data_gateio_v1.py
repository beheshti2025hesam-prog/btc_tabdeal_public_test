"""Gate.io public market-data collector; no credentials or trading endpoints.

REST reconciliation reuses GateioSpotKlineSource, the canonical eight-field
Gate.io contract. WebSocket messages are wake-up notifications only; persisted
candle records always come from the native REST adapter. JSONL history is durable
and is never truncated to the bounded REST fetch window. Normal updates append;
rare historical backfills use a validated atomic rewrite. Gaps/conflicts fail closed.
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import websocket

from .native_ohlcv_gateio_v1 import GateioSpotKlineSource

ROOT = Path(__file__).resolve().parents[1]
WS_URL = "wss://api.gateio.ws/ws/v4/"
SYMBOL = "BTC_USDT"          # persisted Gate.io venue symbol
INTERNAL_SYMBOL = "BTCUSDT"  # explicit key accepted by the native adapter
INTERVAL = os.environ.get("HES_GLOBAL_CANDLES_INTERVAL", "15m")
INTERVAL_SECONDS_BY_NAME = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
if INTERVAL not in INTERVAL_SECONDS_BY_NAME:
    raise RuntimeError(f"Unsupported HES candle interval: {INTERVAL}")
INTERVAL_SECONDS = INTERVAL_SECONDS_BY_NAME[INTERVAL]
SOURCE = "gateio_public_spot"
def persisted_candle_limit(interval: str) -> int:
    """Keep one full 24h outcome horizon plus one hour of recovery margin for 1m."""
    return 1500 if interval == "1m" else 500


MAX_PERSISTED_CANDLES = persisted_candle_limit(INTERVAL)
# Bounded steady-state read window; this never limits on-disk retention.
LIVE_WINDOW_CANDLES = 5000
DEFAULT_OUTPUTS = {
    "1m": ROOT / "data/forward/global_market_candles_1m_v1.jsonl",
    "15m": ROOT / "data/forward/global_market_candles_v1.jsonl",
    "1h": ROOT / "data/forward/global_market_candles_1h_v1.jsonl",
    "4h": ROOT / "data/forward/global_market_candles_4h_v1.jsonl",
}
OUTPUT = Path(os.environ.get("HES_GLOBAL_CANDLES_OUTPUT", str(DEFAULT_OUTPUTS[INTERVAL]))).expanduser()
STOP = False


def _stop(_signum, _frame):
    global STOP
    STOP = True


def normalize_row(row: list[Any] | tuple[Any, ...], *, now: int | None = None) -> dict[str, Any]:
    """Validate a WS close notification; its values are never persisted directly."""
    if not isinstance(row, (list, tuple)) or len(row) != 7:
        raise ValueError("Gate WS candle row must contain exactly seven fields")
    try:
        ts = int(row[0])
        quote_vol, close, high, low, open_, volume = (Decimal(str(x)) for x in row[1:7])
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid numeric WS candle field") from exc
    if ts < 0 or ts % INTERVAL_SECONDS:
        raise ValueError("Misaligned or negative WS candle timestamp")
    if min(open_, high, low, close) <= 0 or min(volume, quote_vol) < 0:
        raise ValueError("Invalid WS candle price or volume")
    if high < max(open_, close, low) or low > min(open_, close, high):
        raise ValueError("Inconsistent WS OHLC bounds")
    now_s = int(time.time()) if now is None else int(now)
    return {
        "schema": "hes_global_candle_v1",
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": INTERVAL,
        "open_time": ts,
        "close_time": ts + INTERVAL_SECONDS,
        "open": str(open_),
        "high": str(high),
        "low": str(low),
        "close": str(close),
        "volume": str(volume),
        "quote_volume": str(quote_vol),
        "closed": ts + INTERVAL_SECONDS <= now_s,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _native_candle_to_record(candle, fetched_at_ms: int) -> dict[str, Any]:
    observed_at = datetime.fromtimestamp(fetched_at_ms / 1000, timezone.utc).isoformat()
    return {
        "schema": "hes_global_candle_v1",
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": INTERVAL,
        "open_time": candle.open_time_ms // 1000,
        "close_time": (candle.close_time_ms + 1) // 1000,
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "quote_volume": str(candle.quote_volume),
        "closed": candle.closed is True,
        "observed_at": observed_at,
    }


def fetch_recent_closed(source: GateioSpotKlineSource | None = None, *, now: int | None = None) -> list[dict[str, Any]]:
    """Fetch closed REST candles through the shared, versioned native adapter."""
    source = source or GateioSpotKlineSource()
    if INTERVAL != "1m" or MAX_PERSISTED_CANDLES <= 1000:
        kwargs = {"symbol": INTERNAL_SYMBOL, "interval": INTERVAL, "limit": MAX_PERSISTED_CANDLES}
        if now is not None:
            kwargs["as_of_ms"] = int(now) * 1000
        batch = source.fetch(**kwargs)
        if batch.gaps:
            raise ValueError(f"Gate.io REST backfill contains {len(batch.gaps)} candle gap(s)")
        return [_native_candle_to_record(candle, batch.fetched_at_ms) for candle in batch.candles]

    # Gate.io Spot REST caps one response at 1,000 candles. Fetch the newest
    # page, then the immediately preceding page; validate continuity before
    # exposing the 1,500-bar window required by the 24h paper-outcome horizon.
    now_ms = int(now * 1000) if now is not None else int(time.time() * 1000)
    newest = source.fetch(
        symbol=INTERNAL_SYMBOL, interval=INTERVAL, limit=1000,
        end_time_ms=now_ms, as_of_ms=now_ms,
    )
    if newest.gaps:
        raise ValueError(f"Gate.io REST newest page contains {len(newest.gaps)} candle gap(s)")
    candles = list(newest.candles)
    remaining = MAX_PERSISTED_CANDLES - len(candles)
    if remaining > 0 and candles:
        older = source.fetch(
            symbol=INTERNAL_SYMBOL, interval=INTERVAL, limit=remaining,
            end_time_ms=candles[0].open_time_ms - 1, as_of_ms=now_ms,
        )
        if older.gaps:
            raise ValueError(f"Gate.io REST older page contains {len(older.gaps)} candle gap(s)")
        candles = list(older.candles) + candles
    candles.sort(key=lambda item: item.open_time_ms)
    for previous, current in zip(candles, candles[1:]):
        if current.open_time_ms - previous.open_time_ms != INTERVAL_SECONDS * 1000:
            raise ValueError("Gate.io paginated 1m candle window is incomplete")
    fetched_at_ms = max((newest.fetched_at_ms,), default=now_ms)
    return [_native_candle_to_record(candle, fetched_at_ms) for candle in candles]


def _validate_persisted_candle(candle: dict[str, Any]) -> int:
    if not isinstance(candle, dict):
        raise ValueError("Persisted candle must be an object")
    if (candle.get("schema"), candle.get("source"), candle.get("symbol"), candle.get("timeframe")) != (
        "hes_global_candle_v1", SOURCE, SYMBOL, INTERVAL
    ):
        raise ValueError("Persisted candle identity mismatch")
    if candle.get("closed") is not True:
        raise ValueError("Only closed candles may be persisted")
    ts = candle.get("open_time")
    close_time = candle.get("close_time")
    if type(ts) is not int or type(close_time) is not int or ts < 0 or ts % INTERVAL_SECONDS:
        raise ValueError("Invalid persisted candle timestamp")
    if close_time != ts + INTERVAL_SECONDS:
        raise ValueError("Persisted candle close_time mismatch")
    try:
        quote, close, high, low, open_, volume = (
            Decimal(candle[key]) for key in ("quote_volume", "close", "high", "low", "open", "volume")
        )
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid persisted candle numeric field") from exc
    if not all(value.is_finite() for value in (quote, close, high, low, open_, volume)):
        raise ValueError("Non-finite persisted candle numeric field")
    if min(open_, high, low, close) <= 0 or min(volume, quote) < 0:
        raise ValueError("Invalid persisted candle price or volume")
    if high < max(open_, close, low) or low > min(open_, close, high):
        raise ValueError("Invalid persisted candle OHLC bounds")
    return ts


def _read_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                candle = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("Malformed persisted Gate.io candle JSONL") from exc
            _validate_persisted_candle(candle)
            rows.append(candle)
    return rows



def _read_existing_tail(path: Path, max_rows: int = LIVE_WINDOW_CANDLES) -> list[dict[str, Any]]:
    """Read a bounded validated tail for steady-state updates on long-lived JSONL."""
    if not path.exists():
        return []
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("max_rows must be positive")
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        chunks: list[bytes] = []
        data = b""
        while position > 0 and data.count(b"\n") <= max_rows:
            size = min(64 * 1024, position)
            position -= size
            handle.seek(position)
            chunks.insert(0, handle.read(size))
            data = b"".join(chunks)
    lines = data.splitlines()
    if position > 0 and lines:
        lines = lines[1:]
    rows: list[dict[str, Any]] = []
    previous = None
    for line_number, line in enumerate(lines[-max_rows:], 1):
        if not line.strip():
            continue
        try:
            candle = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("Malformed persisted Gate.io candle JSONL") from exc
        ts = _validate_persisted_candle(candle)
        if previous is not None and ts == previous:
            if rows and not _same_candle(rows[-1], candle):
                raise ValueError(f"Conflicting persisted Gate.io candle for open_time={ts}")
            raise ValueError(f"Duplicate persisted Gate.io candle for open_time={ts}")
        if previous is not None and ts < previous:
            raise ValueError(f"Persisted candle order invalid at tail line {line_number}")
        rows.append(candle)
        previous = ts
    return rows


def _atomic_rewrite_history(output: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically rewrite a complete history only for an explicit historical backfill."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            for candle in rows:
                handle.write(json.dumps(candle, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if output.exists():
            os.chmod(temp, output.stat().st_mode & 0o777)
        os.replace(temp, output)
        try:
            directory_fd = os.open(output.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if temp.exists():
            temp.unlink()


def _same_candle(left: dict[str, Any], right: dict[str, Any]) -> bool:
    exact_fields = ("schema", "source", "symbol", "timeframe", "open_time", "close_time", "closed")
    if any(left.get(field) != right.get(field) for field in exact_fields):
        return False

    numeric_fields = ("open", "high", "low", "close", "volume", "quote_volume")
    try:
        for field in numeric_fields:
            left_value = Decimal(str(left[field]))
            right_value = Decimal(str(right[field]))
            if not left_value.is_finite() or not right_value.is_finite() or left_value != right_value:
                return False
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False
    return True


def _append_new(candles: list[dict[str, Any]], last_ts: int, output: Path = OUTPUT) -> int:
    """Idempotently append closed candles without truncating durable history.

    The bounded tail is sufficient for normal REST overlap checks. If an
    incoming candle is older than the tail or fills a historical gap, the
    complete file is read and validated before an atomic sorted rewrite.
    Conflicting same-key payloads always fail closed.
    """
    existing = _read_existing_tail(output)
    merged: dict[int, dict[str, Any]] = {}
    for candle in existing:
        ts = _validate_persisted_candle(candle)
        if ts in merged:
            raise ValueError(f"Duplicate persisted Gate.io candle for open_time={ts}")
        merged[ts] = candle

    incoming: dict[int, dict[str, Any]] = {}
    for candle in candles:
        if not candle.get("closed"):
            continue
        ts = _validate_persisted_candle(candle)
        previous = incoming.get(ts)
        if previous is not None and not _same_candle(previous, candle):
            raise ValueError(f"Conflicting incoming Gate.io candle for open_time={ts}")
        incoming[ts] = candle
        previous = merged.get(ts)
        if previous is not None:
            if not _same_candle(previous, candle):
                raise ValueError(f"Conflicting Gate.io candle for open_time={ts}")
            continue
        merged[ts] = candle

    ordered_tail = [merged[ts] for ts in sorted(merged)]
    for previous, current in zip(ordered_tail, ordered_tail[1:]):
        if current["open_time"] - previous["open_time"] != INTERVAL_SECONDS:
            raise ValueError(
                f"Unresolved Gate.io candle gap: {previous['open_time']} -> {current['open_time']}"
            )
    if not ordered_tail:
        return last_ts

    existing_times = {row["open_time"] for row in existing}
    added_times = set(merged) - existing_times
    if not added_times:
        return int(ordered_tail[-1]["open_time"])

    existing_max = max(existing_times, default=None)
    append_only = existing_max is None or min(added_times) > existing_max
    if append_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and existing_max is not None:
            with output.open("rb") as check:
                check.seek(0, os.SEEK_END)
                if check.tell():
                    check.seek(-1, os.SEEK_END)
                    if check.read(1) != b"\n":
                        raise ValueError("Persisted Gate.io candle file lacks final newline")
            new_rows = [merged[ts] for ts in sorted(added_times)]
            with output.open("a", encoding="utf-8") as handle:
                for candle in new_rows:
                    handle.write(json.dumps(candle, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return int(new_rows[-1]["open_time"])
        _atomic_rewrite_history(output, ordered_tail)
        return int(ordered_tail[-1]["open_time"])

    # Rare historical backfill: inspect the complete file, never just the tail.
    full_existing = _read_existing(output)
    full_map: dict[int, dict[str, Any]] = {}
    for candle in full_existing:
        ts = _validate_persisted_candle(candle)
        if ts in full_map:
            raise ValueError(f"Duplicate persisted Gate.io candle for open_time={ts}")
        full_map[ts] = candle
    for ts, candle in incoming.items():
        previous = full_map.get(ts)
        if previous is not None:
            if not _same_candle(previous, candle):
                raise ValueError(f"Conflicting Gate.io candle for open_time={ts}")
        else:
            full_map[ts] = candle
    ordered_full = [full_map[ts] for ts in sorted(full_map)]
    for previous, current in zip(ordered_full, ordered_full[1:]):
        if current["open_time"] - previous["open_time"] != INTERVAL_SECONDS:
            raise ValueError(
                f"Unresolved Gate.io candle gap: {previous['open_time']} -> {current['open_time']}"
            )
    if ordered_full != full_existing:
        _atomic_rewrite_history(output, ordered_full)
    return int(ordered_full[-1]["open_time"])


def _last_saved_ts(path: Path) -> int:
    rows = _read_existing(path)
    return int(rows[-1]["open_time"]) if rows else -1


def normalize_ws_message(message: dict[str, Any], *, now: int | None = None) -> dict[str, Any] | None:
    if message.get("channel") != "spot.candlesticks" or message.get("event") != "update":
        return None
    result = message.get("result")
    if not isinstance(result, dict) or result.get("n") not in (f"{INTERVAL}_{SYMBOL}", INTERVAL):
        return None
    # Gate.io WS: v=quote volume, a=base volume. Never substitute one for the other.
    required = ("t", "v", "a", "c", "h", "l", "o")
    if any(result.get(key) is None for key in required):
        return None
    row = [result["t"], result["v"], result["c"], result["h"], result["l"], result["o"], result["a"]]
    try:
        return normalize_row(row, now=now)
    except (ValueError, TypeError):
        return None


def run() -> None:
    global STOP
    STOP = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    source = GateioSpotKlineSource()
    last_ts = _last_saved_ts(OUTPUT)
    print(
        f"HES_GLOBAL_MARKET_START source={SOURCE} symbol={SYMBOL} timeframe={INTERVAL} last_ts={last_ts}",
        flush=True,
    )
    backoff = 2
    while not STOP:
        ws = None
        try:
            last_ts = _append_new(fetch_recent_closed(source), last_ts)
            ws = websocket.create_connection(WS_URL, timeout=12, origin="https://www.gate.com")
            ws.send(
                json.dumps(
                    {
                        "time": int(time.time()),
                        "channel": "spot.candlesticks",
                        "event": "subscribe",
                        "payload": [INTERVAL, SYMBOL],
                    }
                )
            )
            deadline = time.monotonic() + 10
            last_rest_sync = time.monotonic()
            subscribed = False
            while not STOP:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic() > deadline and not subscribed:
                        raise RuntimeError("Gate.io WebSocket subscription timed out")
                    raw = None
                if raw is not None:
                    message = json.loads(raw)
                    if message.get("event") == "subscribe":
                        if (message.get("result") or {}).get("status") != "success":
                            raise RuntimeError("Gate.io WebSocket subscription rejected")
                        subscribed = True
                        deadline = time.monotonic() + 10
                        backoff = 2
                        print("HES_GLOBAL_MARKET_WS_SUBSCRIBED", flush=True)
                        continue
                    candle = normalize_ws_message(message)
                    if candle is not None and candle["closed"]:
                        # WS is a wake-up only. Persist the final closed bar from the
                        # shared eight-field REST adapter, never from WS payloads.
                        last_ts = _append_new(fetch_recent_closed(source), last_ts)
                        last_rest_sync = time.monotonic()
                # Reconcile at least every 20s even if WS sends a continuous stream
                # of malformed/unrelated messages and recv() never times out.
                if subscribed and time.monotonic() - last_rest_sync >= 20:
                    last_ts = _append_new(fetch_recent_closed(source), last_ts)
                    last_rest_sync = time.monotonic()
        except Exception as exc:
            print(f"HES_GLOBAL_MARKET_RECONNECT error={type(exc).__name__} wait_s={backoff}", flush=True)
            if not STOP:
                time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
    print("HES_GLOBAL_MARKET_STOP", flush=True)


if __name__ == "__main__":
    run()
