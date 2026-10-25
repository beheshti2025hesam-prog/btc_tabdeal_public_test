from datetime import datetime, timezone

from scripts.analyze_gateio_snapshot_v1 import snapshot


def rows(current_close):
    out = []
    for i in range(21):
        close = current_close if i == 20 else 95.0
        high = 112.0 if i == 20 else 110.0 if i == 0 else 100.0
        low = 90.0
        out.append({
            "open_time": i * 900,
            "close_time": (i + 1) * 900,
            "open": str(close),
            "high": str(high),
            "low": str(low),
            "close": str(close),
            "volume": "10",
            "quote_volume": str(close * 10),
            "closed": True,
            "observed_at": datetime.fromtimestamp((i + 1) * 900, timezone.utc).isoformat(),
        })
    return out


def test_breakout_uses_exactly_twenty_prior_closed_bars():
    result = snapshot("15m", rows(105.0))
    assert result["breakout_lookback_bars"] == 20
    assert result["prior20_high"] == 110.0
    assert result["close_breakout20"] == "NONE"


def test_close_above_all_twenty_prior_bars_is_up_breakout():
    result = snapshot("15m", rows(111.0))
    assert result["close_breakout20"] == "UP"
