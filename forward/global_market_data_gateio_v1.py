"""HES public global-market candle feed using Gate.io's public API.
Market data only: no credentials, account endpoints, order placement, or trading.
Writes normalized, closed BTC_USDT 15m candles to JSONL. Reconnects with REST
backfill and idempotent candle-open-time keys. Does not modify legacy collectors.
"""
from __future__ import annotations
import fcntl, json, os, signal, tempfile, time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import requests
import websocket

REST_URL = 'https://api.gateio.ws/api/v4/spot/candlesticks'
WS_URL = 'wss://api.gateio.ws/ws/v4/'
SYMBOL = os.environ.get('HES_GLOBAL_CANDLES_SYMBOL', 'BTC_USDT')
SUPPORTED_SYMBOLS = frozenset({'BTC_USDT', 'ETH_USDT', 'SOL_USDT'})
if SYMBOL not in SUPPORTED_SYMBOLS:
    raise RuntimeError(f'Unsupported HES Gate.io symbol: {SYMBOL}')
INTERVAL = os.environ.get('HES_GLOBAL_CANDLES_INTERVAL', '15m')
INTERVAL_SECONDS_BY_NAME = {'15m': 900, '1h': 3600, '4h': 14400}
if INTERVAL not in INTERVAL_SECONDS_BY_NAME:
    raise RuntimeError(f'Unsupported HES candle interval: {INTERVAL}')
INTERVAL_SECONDS = INTERVAL_SECONDS_BY_NAME[INTERVAL]
# Bound in-memory merge reads without truncating the append-only candle history.
LIVE_WINDOW_CANDLES = 5000
SOURCE = 'gateio_public_spot'
DEFAULT_OUTPUTS = {'15m': '/opt/hes-trade-agent/data/forward/global_market_candles_v1.jsonl',
                   '1h': '/opt/hes-trade-agent/data/forward/global_market_candles_1h_v1.jsonl',
                   '4h': '/opt/hes-trade-agent/data/forward/global_market_candles_4h_v1.jsonl'}
DEFAULT_OUTPUT = (DEFAULT_OUTPUTS[INTERVAL] if SYMBOL == 'BTC_USDT' else
                  f'/opt/hes-trade-agent/data/forward/global_market_candles_{SYMBOL}_{INTERVAL}_v1.jsonl')
OUTPUT = Path(os.environ.get('HES_GLOBAL_CANDLES_OUTPUT', DEFAULT_OUTPUT))
STOP = False

def _stop(_signum, _frame):
    global STOP
    STOP = True

def normalize_row(row: list[Any] | tuple[Any, ...], *, now: int | None = None) -> dict[str, Any]:
    # Gate REST: [timestamp, quote_volume, close, high, low, open, base_volume, closed?]
    if len(row) < 7:
        raise ValueError('Gate candle row has fewer than 7 fields')
    try:
        ts = int(row[0])
        quote_vol, close, high, low, open_, volume = (Decimal(str(x)) for x in row[1:7])
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError('Invalid numeric candle field') from exc
    if ts < 0 or min(open_, high, low, close) <= 0 or min(volume, quote_vol) < 0:
        raise ValueError('Negative timestamp, price, or volume')
    if high < max(open_, close, low) or low > min(open_, close, high):
        raise ValueError('Inconsistent OHLC bounds')
    now_s = int(time.time()) if now is None else int(now)
    closed = ts + INTERVAL_SECONDS <= now_s
    return {'schema':'hes_global_candle_v1','source':SOURCE,'symbol':SYMBOL,
            'timeframe':INTERVAL,'open_time':ts,'close_time':ts+INTERVAL_SECONDS,
            'open':str(open_),'high':str(high),'low':str(low),'close':str(close),
            'volume':str(volume),'quote_volume':str(quote_vol),'closed':closed,
            'observed_at':datetime.now(timezone.utc).isoformat()}

def fetch_recent_closed(session: requests.Session | None = None, *, now: int | None = None) -> list[dict[str, Any]]:
    s = session or requests.Session()
    response = s.get(REST_URL, params={'currency_pair':SYMBOL,'interval':INTERVAL,'limit':1000}, timeout=(4,8))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError('Unexpected Gate REST payload')
    rows = [normalize_row(row, now=now) for row in payload]
    by_ts = {item['open_time']:item for item in rows if item['closed']}
    return [by_ts[key] for key in sorted(by_ts)]


def _missing_candle_ranges(saved: dict[int, dict[str, Any]], *, max_ranges: int = 10) -> list[tuple[int, int]]:
    """Return bounded inclusive (from, to) ranges for missing candle open times."""
    if max_ranges < 1:
        raise ValueError('max_ranges must be positive')
    keys = sorted(saved)
    ranges: list[tuple[int, int]] = []
    for left, right in zip(keys, keys[1:]):
        start = left + INTERVAL_SECONDS
        end = right - INTERVAL_SECONDS
        while start <= end and len(ranges) < max_ranges:
            chunk_end = min(end, start + 999 * INTERVAL_SECONDS)
            ranges.append((start, chunk_end))
            start = chunk_end + INTERVAL_SECONDS
        if len(ranges) >= max_ranges:
            break
    return ranges


def fetch_closed_range(session: requests.Session, start_open_time: int, end_open_time: int,
                       *, now: int | None = None) -> list[dict[str, Any]]:
    """Fetch one documented Gate candle time range (at most 1,000 points)."""
    if start_open_time < 0 or end_open_time < start_open_time:
        raise ValueError('invalid candle backfill range')
    if start_open_time % INTERVAL_SECONDS or end_open_time % INTERVAL_SECONDS:
        raise ValueError('unaligned candle backfill range')
    count = (end_open_time - start_open_time) // INTERVAL_SECONDS + 1
    if count > 1000:
        raise ValueError('candle backfill range exceeds Gate 1,000-point maximum')
    response = session.get(
        REST_URL,
        params={'currency_pair': SYMBOL, 'interval': INTERVAL,
                'from': start_open_time, 'to': end_open_time},
        timeout=(4, 8),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError('Unexpected Gate backfill payload')
    by_ts = {}
    for raw in payload:
        candle = normalize_row(raw, now=now)
        ts = candle['open_time']
        if start_open_time <= ts <= end_open_time and candle['closed']:
            if ts in by_ts and _semantic_candle(by_ts[ts]) != _semantic_candle(candle):
                raise ValueError(f'Conflicting Gate backfill candle at open_time={ts}')
            by_ts[ts] = candle
    return [by_ts[ts] for ts in sorted(by_ts)]


def _backfill_missing_history(session: requests.Session, output: Path = OUTPUT,
                              *, max_ranges: int = 10) -> int:
    """Repair historical candle gaps with bounded Gate time-range requests."""
    saved = _read_saved_candles(output)
    ranges = _missing_candle_ranges(saved, max_ranges=max_ranges)
    repaired = 0
    for start, end in ranges:
        candles = fetch_closed_range(session, start, end)
        expected = (end - start) // INTERVAL_SECONDS + 1
        returned = {int(row['open_time']) for row in candles}
        _append_new(candles, max(saved, default=-1), output)
        if len(returned) == expected and all(
            ts in returned for ts in range(start, end + 1, INTERVAL_SECONDS)
        ):
            repaired += expected
            print(f'HES_GLOBAL_CANDLE_BACKFILL_REPAIRED symbol={SYMBOL} tf={INTERVAL} from={start} to={end} count={expected}', flush=True)
        else:
            missing = expected - len(returned)
            print(f'HES_GLOBAL_CANDLE_BACKFILL_INCOMPLETE symbol={SYMBOL} tf={INTERVAL} from={start} to={end} missing={missing}', flush=True)
    return repaired


def _last_saved_ts(path: Path) -> int:
    if not path.exists(): return -1
    try:
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END); size=f.tell(); f.seek(max(0,size-65536)); lines=f.read().splitlines()
        for line in reversed(lines):
            try:
                obj=json.loads(line)
                if obj.get('source') == SOURCE and obj.get('symbol') == SYMBOL and obj.get('timeframe') == INTERVAL:
                    return int(obj['open_time'])
            except (ValueError, KeyError, TypeError): pass
    except OSError: pass
    return -1

def _semantic_candle(candle: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(candle.get(key) for key in (
        'schema', 'source', 'symbol', 'timeframe', 'open_time', 'close_time',
        'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'closed',
    ))


def _tail_jsonl_lines(path: Path, max_lines: int = LIVE_WINDOW_CANDLES) -> list[str]:
    """Read a bounded tail without scanning the full long-lived append-only file."""
    if max_lines < 1:
        raise ValueError('max_lines must be positive')
    with path.open('rb') as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        chunks: list[bytes] = []
        data = b''
        while position > 0 and data.count(b'\n') <= max_lines:
            size = min(64 * 1024, position)
            position -= size
            handle.seek(position)
            chunks.insert(0, handle.read(size))
            data = b''.join(chunks)
    lines = data.splitlines()
    if position > 0 and lines:
        lines = lines[1:]
    return [line.decode('utf-8') for line in lines[-max_lines:] if line.strip()]


def _parse_saved_candles(lines: list[str]) -> dict[int, dict[str, Any]]:
    saved: dict[int, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, 1):
        try:
            candle = json.loads(line)
            ts = int(candle['open_time'])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Existing candle file is malformed at tail line {line_number}') from exc
        if (candle.get('source') != SOURCE or candle.get('symbol') != SYMBOL
                or candle.get('timeframe') != INTERVAL or candle.get('closed') is not True):
            raise ValueError(f'Existing candle identity/state mismatch at tail line {line_number}')
        if ts < 0 or ts % INTERVAL_SECONDS or int(candle.get('close_time', -1)) != ts + INTERVAL_SECONDS:
            raise ValueError(f'Existing candle timestamp invalid at tail line {line_number}')
        if ts in saved and _semantic_candle(saved[ts]) != _semantic_candle(candle):
            raise ValueError(f'Conflicting candle identity at open_time={ts}')
        saved[ts] = candle
    return saved


def _read_saved_candles(output: Path) -> dict[int, dict[str, Any]]:
    if not output.exists():
        return {}
    return _parse_saved_candles(_tail_jsonl_lines(output))


def _read_all_saved_candles(output: Path) -> dict[int, dict[str, Any]]:
    if not output.exists():
        return {}
    with output.open('r', encoding='utf-8') as handle:
        return _parse_saved_candles([line for line in handle if line.strip()])



def _append_new(candles: list[dict[str, Any]], last_ts: int, output: Path = OUTPUT) -> int:
    """Idempotently merge closed candles by (source, symbol, timeframe, open_time).

    Gate candle open_time is the candle identity within this exact product and
    interval; it is not a generic trade/order-book sequence. Historical rows
    arriving after reconnect are inserted by an atomic sorted rewrite so the
    reader never sees out-of-order JSONL. Conflicting same-key payloads fail closed.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.with_name(output.name + '.lock')
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        saved = _read_saved_candles(output)
        before = set(saved)
        for candle in candles:
            if candle.get('source') != SOURCE or candle.get('symbol') != SYMBOL or candle.get('timeframe') != INTERVAL:
                raise ValueError('Incoming candle identity mismatch')
            if candle.get('closed') is not True:
                continue
            ts = int(candle['open_time'])
            if ts < 0 or ts % INTERVAL_SECONDS != 0:
                raise ValueError(f'Invalid candle open_time alignment: {ts}')
            if int(candle.get('close_time', -1)) != ts + INTERVAL_SECONDS:
                raise ValueError(f'Invalid candle close_time: {ts}')
            existing = saved.get(ts)
            if existing is not None:
                if _semantic_candle(existing) != _semantic_candle(candle):
                    raise ValueError(f'Conflicting candle identity at open_time={ts}')
                continue
            saved[ts] = candle

        added = set(saved) - before
        needs_backfill_rewrite = bool(added) and bool(before) and min(added) < max(before)
        if needs_backfill_rewrite:
            full_saved = _read_all_saved_candles(output)
            full_before = set(full_saved)
            for ts in added:
                candle = saved[ts]
                existing = full_saved.get(ts)
                if existing is not None:
                    if _semantic_candle(existing) != _semantic_candle(candle):
                        raise ValueError(f'Conflicting candle identity at open_time={ts}')
                else:
                    full_saved[ts] = candle
            saved = full_saved
            added = set(saved) - full_before

        if added:
            if needs_backfill_rewrite:
                ordered = [saved[ts] for ts in sorted(saved)]
                fd, tmp_name = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=str(output.parent))
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                        for candle in ordered:
                            handle.write(json.dumps(candle, sort_keys=True, separators=(',', ':')) + '\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                    if output.exists():
                        os.chmod(tmp_name, output.stat().st_mode & 0o777)
                    os.replace(tmp_name, output)
                    dir_fd = os.open(str(output.parent), os.O_DIRECTORY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
            else:
                with output.open('a', encoding='utf-8') as handle:
                    for ts in sorted(added):
                        handle.write(json.dumps(saved[ts], sort_keys=True, separators=(',', ':')) + '\n')
                    handle.flush()
                    os.fsync(handle.fileno())
            for ts in sorted(added):
                print(f"HES_GLOBAL_CANDLE source={SOURCE} symbol={SYMBOL} tf={INTERVAL} open_time={ts} closed=true", flush=True)
        return max(saved, default=last_ts)

def normalize_ws_message(message: dict[str, Any], *, now: int | None = None) -> dict[str, Any] | None:
    if message.get('channel') != 'spot.candlesticks' or message.get('event') != 'update':
        return None
    result = message.get('result')
    if not isinstance(result, dict) or result.get('n') != f'{INTERVAL}_{SYMBOL}':
        return None
    # Gate WS: v=quote volume, a=base volume; n is "<interval>_<pair>".
    row = [result.get('t'), result.get('v', '0'), result.get('c'), result.get('h'),
           result.get('l'), result.get('o'), result.get('a', result.get('v', '0'))]
    try:
        return normalize_row(row, now=now)
    except (ValueError, TypeError):
        return None


def run() -> None:
    signal.signal(signal.SIGTERM, _stop); signal.signal(signal.SIGINT, _stop)
    last_ts = _last_saved_ts(OUTPUT)
    print(f'HES_GLOBAL_MARKET_START source={SOURCE} symbol={SYMBOL} timeframe={INTERVAL} last_ts={last_ts}', flush=True)
    session=requests.Session(); session.headers.update({'User-Agent':'HES-Trade-Agent/1.0 public-market-data'})
    backoff=2
    while not STOP:
        try:
            last_ts = _append_new(fetch_recent_closed(session), last_ts)
            _backfill_missing_history(session, OUTPUT)
            ws=websocket.create_connection(WS_URL, timeout=12, origin='https://www.gate.com')
            ws.send(json.dumps({'time':int(time.time()),'channel':'spot.candlesticks','event':'subscribe','payload':[INTERVAL,SYMBOL]}))
            deadline=time.monotonic()+10
            last_rest_sync=time.monotonic()
            subscribed=False
            while not STOP:
                try: raw=ws.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic()>deadline and not subscribed: raise RuntimeError('WebSocket subscription timed out')
                    # Candlestick WS updates describe the current candle; REST reconciliation
                    # guarantees we persist the just-closed candle even if no final WS tick arrives.
                    if subscribed and time.monotonic()-last_rest_sync >= 20:
                        last_ts=_append_new(fetch_recent_closed(session), last_ts)
                        _backfill_missing_history(session, OUTPUT)
                        last_rest_sync=time.monotonic()
                    continue
                msg=json.loads(raw)
                if msg.get('event')=='subscribe':
                    if (msg.get('result') or {}).get('status')!='success': raise RuntimeError('Gate WebSocket subscription rejected')
                    subscribed=True; deadline=time.monotonic()+10; backoff=2
                    print('HES_GLOBAL_MARKET_WS_SUBSCRIBED', flush=True); continue
                if msg.get('channel')!='spot.candlesticks' or msg.get('event')!='update': continue
                candle=normalize_ws_message(msg)
                if candle is None: continue
                if candle['closed']: last_ts=_append_new([candle], last_ts)
            ws.close()
        except Exception as exc:
            print(f'HES_GLOBAL_MARKET_RECONNECT error={type(exc).__name__} wait_s={backoff}', flush=True)
            time.sleep(backoff); backoff=min(backoff*2,60)
    print('HES_GLOBAL_MARKET_STOP', flush=True)

if __name__=='__main__': run()
