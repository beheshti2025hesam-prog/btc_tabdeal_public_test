from datetime import datetime, timedelta, timezone

from core.models.candle import Candle


class CandleBuilder:
    def __init__(self, timeframe="15m"):
        self.timeframe = self._parse_timeframe(timeframe)

    @staticmethod
    def _parse_timeframe(timeframe):
        if not isinstance(timeframe, str):
            raise ValueError("timeframe must be a string")

        value = timeframe.strip().lower()

        units = {
            "m": 60,
            "h": 3600,
            "d": 86400,
        }

        if len(value) < 2 or value[-1] not in units:
            raise ValueError("unsupported timeframe")

        try:
            amount = int(value[:-1])
        except ValueError as exc:
            raise ValueError("invalid timeframe") from exc

        if amount <= 0:
            raise ValueError("timeframe must be positive")

        return timedelta(seconds=amount * units[value[-1]])

    @staticmethod
    def _bucket_start(timestamp, timeframe):
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        elapsed = timestamp.astimezone(timezone.utc) - epoch
        seconds = int(elapsed.total_seconds())
        interval = int(timeframe.total_seconds())

        bucket_seconds = (seconds // interval) * interval

        return epoch + timedelta(seconds=bucket_seconds)

    def build(self, trades):
        if not trades:
            return []

        ordered = sorted(trades, key=lambda trade: trade.timestamp)

        buckets = {}

        for trade in ordered:
            bucket = self._bucket_start(trade.timestamp, self.timeframe)

            if bucket not in buckets:
                buckets[bucket] = {
                    "timestamp": bucket,
                    "timeframe": self._format_timeframe(),
                    "symbol": trade.symbol,
                    "open": trade.price,
                    "high": trade.price,
                    "low": trade.price,
                    "close": trade.price,
                    "volume": 0.0,
                    "trade_count": 0,
                }

            candle = buckets[bucket]

            if trade.symbol != candle["symbol"]:
                raise ValueError("multiple symbols cannot share one CandleBuilder")

            candle["high"] = max(candle["high"], trade.price)
            candle["low"] = min(candle["low"], trade.price)
            candle["close"] = trade.price
            candle["volume"] += trade.quantity
            candle["trade_count"] += 1

        return [
            Candle(**data)
            for _, data in sorted(buckets.items())
        ]

    def _format_timeframe(self):
        seconds = int(self.timeframe.total_seconds())

        if seconds % 86400 == 0:
            return f"{seconds // 86400}d"

        if seconds % 3600 == 0:
            return f"{seconds // 3600}h"

        return f"{seconds // 60}m"
