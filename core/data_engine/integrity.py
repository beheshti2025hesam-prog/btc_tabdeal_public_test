"""
HES Trade Agent - Read-only Data Integrity Audit.

Sequence-like values are descriptive metadata unless an exact venue/channel
contract grants identity, ordering, and continuity capabilities. This generic
audit deliberately makes no such inference.
"""
from collections import defaultdict
from typing import Iterable
from core.models.trade import CanonicalTrade


class IntegrityAudit:
    """Audit normalized event identity and report opaque sequence diagnostics."""

    def audit(self, trades: Iterable[CanonicalTrade]) -> dict:
        groups = defaultdict(list)
        for trade in trades:
            groups[(trade.exchange, trade.symbol)].append(trade)
        reports = {key: self._audit_group(group) for key, group in groups.items()}
        return {
            "total_trades": sum(r["total_trades"] for r in reports.values()),
            "groups": reports,
        }

    @staticmethod
    def _audit_group(trades: list[CanonicalTrade]) -> dict:
        by_timestamp = sorted(trades, key=lambda trade: trade.timestamp)
        sequenced = [t for t in trades if t.sequence is not None]
        sequence_values = [t.sequence for t in sequenced]
        unique_values = set(sequence_values)
        event_ids = {t.event_id for t in trades}
        return {
            "total_trades": len(trades),
            "unique_event_ids": len(event_ids),
            "duplicate_event_id_count": len(trades) - len(event_ids),
            "sequenced_trades": len(sequenced),
            "unique_sequence_values": len(unique_values),
            "repeated_sequence_value_count": len(sequence_values) - len(unique_values),
            "sequence_semantics_status": "UNKNOWN",
            "sequence_ordering_status": "UNKNOWN",
            "sequence_identity_status": "UNKNOWN",
            "sequence_gap_count": None,
            "sequence_gap_total": None,
            "largest_sequence_gap": None,
            "duplicate_sequence_count": None,
            "backward_sequence_count": None,
            "timestamp_backward_count": None,
            "min_sequence_value": None,
            "max_sequence_value": None,
            "first_timestamp": by_timestamp[0].timestamp if by_timestamp else None,
            "last_timestamp": by_timestamp[-1].timestamp if by_timestamp else None,
        }
