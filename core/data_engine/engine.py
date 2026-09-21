"""
Mother Agent - Data Engine
Data Engine v1.0
"""

from typing import List

from core.data_engine.deduplicator import TradeDeduplicator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.models.trade import CanonicalTrade


class DataEngine:
    """
    Unified Raw Data processing pipeline.

    Pipeline:

    Reader
        ↓
    Validator
        ↓
    Normalizer
        ↓
    Deduplicator
        ↓
    Timestamp Ordering

    Raw Data is read-only and is never modified.
    """

    def __init__(
        self,
        reader: RawDataReader | None = None,
        validator: RawDataValidator | None = None,
        normalizer: RawDataNormalizer | None = None,
        deduplicator: TradeDeduplicator | None = None,
    ):
        self.reader = reader or RawDataReader()
        self.validator = validator or RawDataValidator()
        self.normalizer = normalizer or RawDataNormalizer()
        self.deduplicator = (
            deduplicator or TradeDeduplicator()
        )

    def load(self) -> List[CanonicalTrade]:
        """
        Read, validate, normalize, deduplicate,
        and timestamp-sort all available Raw Data.

        Invalid rows are skipped.

        Returns:
            A timestamp-ordered list of unique CanonicalTrade objects.
        """

        canonical_trades = []

        for row in self.reader.read_all():
            errors = self.validator.validate_row(row)

            if errors:
                continue

            trade = self.normalizer.normalize_row(row)

            canonical_trades.append(trade)

        unique_trades = self.deduplicator.deduplicate(
            canonical_trades
        )

        return sorted(
            unique_trades,
            key=lambda trade: trade.timestamp,
        )
