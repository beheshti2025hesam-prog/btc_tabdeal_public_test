"""
HES Trade Agent - Read-only Data Integrity Audit.
"""
from collections import defaultdict
from typing import Iterable
from core.models.trade import CanonicalTrade

class IntegrityAudit:
    """Audit sequence and timestamp consistency by exchange/symbol."""
    def audit(self, trades: Iterable[CanonicalTrade]) -> dict:
        groups = defaultdict(list)
        for trade in trades:
            groups[(trade.exchange, trade.symbol)].append(trade)
        reports = {key: self._audit_group(group) for key, group in groups.items()}
        return {"total_trades": sum(r["total_trades"] for r in reports.values()), "groups": reports}

    @staticmethod
    def _audit_group(trades: list[CanonicalTrade]) -> dict:
        by_timestamp = sorted(trades, key=lambda trade: trade.timestamp)
        sequenced = [t for t in trades if t.sequence is not None]
        by_sequence = sorted(sequenced, key=lambda trade: trade.sequence)
        sequences = [t.sequence for t in sequenced]
        unique = set(sequences)
        ordered = sorted(unique)
        gaps = [cur - prev - 1 for prev, cur in zip(ordered, ordered[1:]) if cur > prev + 1]
        backward = sum(
            1 for prev, cur in zip(by_timestamp, by_timestamp[1:])
            if prev.sequence is not None and cur.sequence is not None and cur.sequence < prev.sequence
        )
        timestamp_backward = sum(
            1 for prev, cur in zip(by_sequence, by_sequence[1:]) if cur.timestamp < prev.timestamp
        )
        event_ids = {t.event_id for t in trades}
        return {
            "total_trades": len(trades),
            "unique_event_ids": len(event_ids),
            "duplicate_event_id_count": len(trades) - len(event_ids),
            "sequenced_trades": len(sequenced),
            "unique_sequences": len(unique),
            "duplicate_sequence_count": len(sequences) - len(unique),
            "sequence_gap_count": len(gaps),
            "sequence_gap_total": sum(gaps),
            "largest_sequence_gap": max(gaps, default=0),
            "min_sequence": min(unique) if unique else None,
            "max_sequence": max(unique) if unique else None,
            "backward_sequence_count": backward,
            "timestamp_backward_count": timestamp_backward,
            "first_timestamp": by_timestamp[0].timestamp if by_timestamp else None,
            "last_timestamp": by_timestamp[-1].timestamp if by_timestamp else None,
        }
