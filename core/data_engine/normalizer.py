"""
Mother Agent - Raw Data Normalizer
Data Engine v1.0
"""

import hashlib
import math
from datetime import datetime, timezone
from typing import Dict

from core.models.trade import CanonicalTrade


class RawDataNormalizer:
    """
    Converts Raw Trade Rows into CanonicalTrade objects.

    The normalizer is independent from file paths, archive layout,
    physical row order, and storage mechanisms. Source/exchange
    provenance is configurable so the core remains venue-agnostic.
    """

    DEFAULT_SOURCE = "raw_csv"
    DEFAULT_EXCHANGE = "tabdeal"

    def __init__(
        self,
        source: str = DEFAULT_SOURCE,
        exchange: str = DEFAULT_EXCHANGE,
    ) -> None:
        if not source.strip():
            raise ValueError("source must not be empty")
        if not exchange.strip():
            raise ValueError("exchange must not be empty")

        self.source = source
        self.exchange = exchange

    def normalize_row(self, row: Dict[str, str]) -> CanonicalTrade:
        symbol = row["symbol"]
        price = self._parse_float(row["price"], "price")
        quantity = self._parse_float(row["amount"], "amount")
        side = row["side"]
        timestamp = self._parse_timestamp(row["updated"])
        sequence = self._parse_int(row["sequence"], "sequence")

        event_id = self._build_event_id(
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=side,
            timestamp=timestamp,
            sequence=sequence,
        )

        return CanonicalTrade(
            event_id=event_id,
            source=self.source,
            exchange=self.exchange,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=side,
            timestamp=timestamp,
            sequence=sequence,
            ingested_at=None,
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
    def _parse_int(value: str, field_name: str) -> int:
        try:
            return int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid {field_name}: {value!r}") from exc

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        if not value:
            raise ValueError("Invalid timestamp: empty value")

        normalized_value = value
        if normalized_value.endswith("Z"):
            normalized_value = normalized_value[:-1] + "+00:00"

        try:
            timestamp = datetime.fromisoformat(normalized_value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid timestamp: {value!r}") from exc

        if timestamp.tzinfo is None:
            raise ValueError(
                f"Timestamp must be timezone-aware: {value!r}"
            )

        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _build_event_id(
        symbol: str,
        price: float,
        quantity: float,
        side: str,
        timestamp: datetime,
        sequence: int,
    ) -> str:
        """
        Build a deterministic event ID independent of file path,
        archive name, or physical row position.
        """
        payload = "|".join(
            [
                symbol,
                str(price),
                str(quantity),
                side,
                timestamp.isoformat(),
                str(sequence),
            ]
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
