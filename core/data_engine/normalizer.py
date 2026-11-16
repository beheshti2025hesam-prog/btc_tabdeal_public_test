"""
HES Trade Agent - Raw Data Normalizer.
"""
import hashlib
import math
from datetime import datetime, timezone
from typing import Dict

from core.models.trade import CanonicalTrade


class RawDataNormalizer:
    DEFAULT_SOURCE = "raw_csv"
    DEFAULT_EXCHANGE = "tabdeal"

    def __init__(self, source: str = DEFAULT_SOURCE, exchange: str = DEFAULT_EXCHANGE) -> None:
        if not source.strip():
            raise ValueError("source must not be empty")
        if not exchange.strip():
            raise ValueError("exchange must not be empty")
        self.source = source
        self.exchange = exchange
        self._row_ordinal = 0

    def normalize_row(self, row: Dict[str, str]) -> CanonicalTrade:
        symbol = row["symbol"]
        price = self._parse_float(row["price"], "price")
        quantity = self._parse_float(row["amount"], "amount")
        side = row["side"].strip().lower()
        timestamp = self._parse_timestamp(row["updated"])
        # trade.sequence is optional opaque metadata. Preserve the native CSV value.
        sequence = row.get("sequence") or None
        self._row_ordinal += 1
        event_id = self._build_event_id(
            self.source, self.exchange, symbol, price, quantity, side, timestamp, self._row_ordinal
        )
        return CanonicalTrade(
            event_id=event_id, source=self.source, exchange=self.exchange,
            symbol=symbol, price=price, quantity=quantity, side=side,
            timestamp=timestamp, sequence=sequence, ingested_at=None,
        )

    @staticmethod
    def _parse_float(value: str, field_name: str) -> float:
        try:
            parsed = float(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid {field_name}: {value!r}") from exc
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError(f"Invalid {field_name}: {value!r}")
        return parsed

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        if not value:
            raise ValueError("Invalid timestamp: empty value")
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            timestamp = datetime.fromisoformat(normalized)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid timestamp: {value!r}") from exc
        if timestamp.tzinfo is None:
            raise ValueError(f"Timestamp must be timezone-aware: {value!r}")
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _build_event_id(source, exchange, symbol, price, quantity, side, timestamp, row_ordinal) -> str:
        # Row ordinal preserves separate receipt occurrences, including byte-identical rows.
        payload = "|".join([
            source, exchange, symbol, str(price), str(quantity), side,
            timestamp.isoformat(), str(row_ordinal),
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
