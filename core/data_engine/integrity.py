"""
Mother Agent - Data Integrity Audit
Data Foundation v1.0

The auditor is intentionally read-only: it inspects canonical trades and
returns deterministic integrity metrics without modifying raw or canonical data.
"""

from collections import defaultdict
from typing import Iterable

from core.models.trade import CanonicalTrade


class IntegrityAudit:
    """Audit ordering and sequence integrity of canonical trades."""

    def audit(self, trades: Iterable[CanonicalTrade]) -> dict:
        groups = defaultdict(list)

        for trade in trades:
            groups[(trade.exchange, trade.symbol)].append(trade)

        reports = {}

        for key, group in groups.items():
            reports[key] = self._audit_group(group)

        return {
            "total_trades": sum(
                report["total_trades"] for report in reports.values()
            ),
            "groups": reports,
        }

    @staticmethod
    def _audit_group(trades: list[CanonicalTrade]) -> dict:
        by_timestamp = sorted(trades, key=lambda trade: trade.timestamp)

        with_sequence = [
            trade for trade in trades
            if trade.sequence is not None
        ]

        by_sequence = sorted(
            with_sequence,
            key=lambda trade: trade.sequence,
        )

        sequences = [
            trade.sequence
            for trade in with_sequence
        ]

        unique_sequences = set(sequences)

        duplicate_sequence_count = (
            len(sequences) - len(unique_sequences)
        )

        unique_sorted = sorted(unique_sequences)

        sequence_gap_count = sum(
            1
            for previous, current in zip(
                unique_sorted,
                unique_sorted[1:],
            )
            if current > previous + 1
        )

        backward_sequence_count = sum(
            1
            for previous, current in zip(
                by_timestamp,
                by_timestamp[1:],
            )
            if (
                previous.sequence is not None
                and current.sequence is not None
                and current.sequence < previous.sequence
            )
        )

        timestamp_backward_count = sum(
            1
            for previous, current in zip(
                by_sequence,
                by_sequence[1:],
            )
            if current.timestamp < previous.timestamp
        )

        unique_event_ids = {
            trade.event_id
            for trade in trades
        }

        return {
            "total_trades": len(trades),
            "unique_event_ids": len(unique_event_ids),
            "duplicate_event_id_count": (
                len(trades) - len(unique_event_ids)
            ),
            "sequenced_trades": len(with_sequence),
            "unique_sequences": len(unique_sequences),
            "duplicate_sequence_count": duplicate_sequence_count,
            "sequence_gap_count": sequence_gap_count,
            "min_sequence": (
                min(unique_sequences)
                if unique_sequences
                else None
            ),
            "max_sequence": (
                max(unique_sequences)
                if unique_sequences
                else None
            ),
            "backward_sequence_count": backward_sequence_count,
            "timestamp_backward_count": timestamp_backward_count,
            "first_timestamp": (
                by_timestamp[0].timestamp
                if by_timestamp
                else None
            ),
            "last_timestamp": (
                by_timestamp[-1].timestamp
                if by_timestamp
                else None
            ),
        }
