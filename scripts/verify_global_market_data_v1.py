"""Live read-only smoke test; does not access accounts or submit orders."""
from datetime import datetime, timedelta, timezone
import json
from forward.global_market_data_v1 import fetch_closed_klines

bars = fetch_closed_klines(symbol="BTCUSDT", interval="1m", limit=5,
    as_of=datetime.now(timezone.utc), max_latest_age=timedelta(seconds=180))
latest = bars[-1]
print(json.dumps({
    "status": "PASS_READ_ONLY_GLOBAL_MARKET_DATA",
    "source": latest.source,
    "market": latest.market,
    "symbol": latest.symbol,
    "interval": latest.interval,
    "closed_candle_count": len(bars),
    "latest_closed_time_utc": latest.close_time.isoformat(),
    "latest_close": str(latest.close),
    "source_volume_preserved": str(latest.volume),
    "credentials_used": False,
    "order_endpoint_called": False,
}, sort_keys=True))
