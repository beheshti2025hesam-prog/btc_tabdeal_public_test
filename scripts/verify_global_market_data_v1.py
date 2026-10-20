"""Live, read-only smoke check for the public global candle feed."""
from datetime import datetime, timedelta, timezone
import json

from forward.global_market_data_v1 import fetch_closed_klines

candles = fetch_closed_klines(
    symbol="BTCUSDT",
    interval="1m",
    limit=5,
    as_of=datetime.now(timezone.utc),
    max_latest_age=timedelta(seconds=120),
)
latest = candles[-1]
now = datetime.now(timezone.utc)
print(json.dumps({
    "status": "PASS_READ_ONLY_GLOBAL_MARKET_DATA",
    "source": latest.source,
    "venue": latest.venue,
    "market": latest.market,
    "symbol": latest.symbol,
    "interval": latest.interval,
    "closed_candle_count": len(candles),
    "latest_closed_open_time": latest.open_time.isoformat(),
    "latest_closed_close_time": latest.close_time.isoformat(),
    "latest_close": str(latest.close),
    "latest_source_volume_preserved": str(latest.volume),
    "latest_closed_age_seconds": (now - latest.close_time).total_seconds(),
    "credentials_used": False,
    "order_endpoint_called": False,
}, sort_keys=True))
