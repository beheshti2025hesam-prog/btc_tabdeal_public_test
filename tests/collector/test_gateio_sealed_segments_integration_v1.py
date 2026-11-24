from pathlib import Path

from forward.global_market_data_gateio_v1 import (
    _append_new, _last_saved_ts, normalize_row,
)
from forward.global_market_data_reader_v1 import read_closed_candles


def candle(open_time, now):
    # Gate.io wake-up payload order: timestamp, quote volume, close, high, low, open, base volume.
    return normalize_row([open_time, "100", "10", "11", "9", "10", "2"], now=now)


def test_gateio_collector_appends_after_seal_and_reader_merges_history(tmp_path):
    path = tmp_path / "data/forward/global_market_candles_v1.jsonl"
    first = [candle(ts, 10_000) for ts in (0, 900, 1800, 2700)]
    assert _append_new(first, -1, path) == 2700

    from forward.sealed_jsonl_segments_v1 import seal_hot_file, logical_sha256
    seal_hot_file(path)
    assert path.read_bytes() == b""
    assert _last_saved_ts(path) == 2700

    later = candle(3600, 10_000)
    assert _append_new([later], 2700, path) == 3600
    rows = read_closed_candles("15m", root=tmp_path, now=5000, min_bars=5)
    assert [row["open_time"] for row in rows] == [0, 900, 1800, 2700, 3600]
    assert logical_sha256(path)