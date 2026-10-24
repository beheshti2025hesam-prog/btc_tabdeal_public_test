"""Venue-neutral execution adapter contract (v1).

This is a typed boundary only. It contains no HTTP client, credentials, venue
selection, order submission implementation, or live-mode enablement. Every
venue-specific guarantee must be backed by a pinned official contract and
independent review before a concrete adapter can be approved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, runtime_checkable

Side = Literal["LONG", "SHORT"]
OrderType = Literal["MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"]
OrderStatus = Literal[
    "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"
]
MarketType = Literal["SPOT", "MARGIN", "USDM_FUTURES", "COINM_FUTURES", "OTHER"]


def _positive_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


@dataclass(frozen=True)
class ExecutionOrderRequestV1:
    """Immutable normalized intent; venue symbol is explicit, never inferred."""

    venue_id: str
    market_type: MarketType
    analysis_symbol: str
    venue_symbol: str
    symbol_mapping_ref: str
    client_order_id: str
    decision_id: str
    payload_sha256: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None
    stop_loss: Decimal
    take_profit: Decimal
    reduce_only: bool
    time_in_force: str | None = None

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        for field_name in (
            "venue_id", "analysis_symbol", "venue_symbol", "symbol_mapping_ref",
            "client_order_id", "decision_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field_name.upper()}_MISSING")
        if self.market_type not in ("SPOT", "MARGIN", "USDM_FUTURES", "COINM_FUTURES", "OTHER"):
            errors.append("MARKET_TYPE_INVALID")
        if self.side not in ("LONG", "SHORT"):
            errors.append("SIDE_INVALID")
        if self.order_type not in ("MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"):
            errors.append("ORDER_TYPE_INVALID")
        if not _sha256(self.payload_sha256):
            errors.append("PAYLOAD_HASH_INVALID")
        if _positive_decimal(self.quantity) is None:
            errors.append("QUANTITY_INVALID")
        if _positive_decimal(self.stop_loss) is None or _positive_decimal(self.take_profit) is None:
            errors.append("PROTECTIVE_PRICE_INVALID")
        if self.limit_price is not None and _positive_decimal(self.limit_price) is None:
            errors.append("LIMIT_PRICE_INVALID")
        if self.order_type == "LIMIT" and self.limit_price is None:
            errors.append("LIMIT_PRICE_REQUIRED")
        if not isinstance(self.reduce_only, bool):
            errors.append("REDUCE_ONLY_FLAG_INVALID")
        return tuple(dict.fromkeys(errors))


@dataclass(frozen=True)
class ExecutionAdapterCapabilitiesV1:
    """Capabilities remain untrusted until the evidence gate is satisfied."""

    venue_id: str
    market_type: MarketType
    api_contract_version: str
    supported_order_types: tuple[OrderType, ...]
    client_order_id_supported: bool
    idempotent_submit_guaranteed: bool
    supports_reduce_only: bool
    supports_native_protective_orders: bool
    supports_cancel: bool
    supports_order_query: bool
    supports_open_order_query: bool
    supports_position_query: bool
    supports_account_reconciliation: bool
    verification_status: Literal["UNVERIFIED", "VERIFIED"] = "UNVERIFIED"
    official_contract_ref: str = ""
    evidence_sha256: str = ""
    reviewed_revision: str = ""

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not isinstance(self.venue_id, str) or not self.venue_id.strip():
            errors.append("CAPABILITY_VENUE_MISSING")
        if not isinstance(self.api_contract_version, str) or not self.api_contract_version.strip():
            errors.append("API_CONTRACT_VERSION_MISSING")
        if not self.supported_order_types:
            errors.append("SUPPORTED_ORDER_TYPES_MISSING")
        if self.verification_status != "VERIFIED":
            errors.append("CAPABILITIES_NOT_INDEPENDENTLY_VERIFIED")
        if not self.official_contract_ref.strip():
            errors.append("OFFICIAL_CONTRACT_EVIDENCE_MISSING")
        if not _sha256(self.evidence_sha256):
            errors.append("CAPABILITY_EVIDENCE_HASH_INVALID")
        if not self.reviewed_revision.strip():
            errors.append("INDEPENDENT_REVIEW_REVISION_MISSING")
        if self.client_order_id_supported is not True:
            errors.append("CLIENT_ORDER_ID_NOT_SUPPORTED")
        if self.idempotent_submit_guaranteed is not True:
            errors.append("IDEMPOTENT_SUBMIT_NOT_PROVEN")
        if self.supports_order_query is not True:
            errors.append("ORDER_QUERY_NOT_SUPPORTED")
        if self.supports_open_order_query is not True:
            errors.append("OPEN_ORDER_QUERY_NOT_SUPPORTED")
        if self.supports_position_query is not True:
            errors.append("POSITION_QUERY_NOT_SUPPORTED")
        if self.supports_account_reconciliation is not True:
            errors.append("ACCOUNT_RECONCILIATION_NOT_SUPPORTED")
        if self.supports_native_protective_orders is not True:
            errors.append("NATIVE_PROTECTIVE_ORDERS_NOT_SUPPORTED")
        if self.supports_cancel is not True:
            errors.append("CANCEL_NOT_SUPPORTED")
        return tuple(dict.fromkeys(errors))


@dataclass(frozen=True)
class VenueOrderSnapshotV1:
    """Normalized venue acknowledgement/query result with raw-response provenance."""

    venue_id: str
    market_type: MarketType
    venue_symbol: str
    client_order_id: str
    venue_order_id: str | None
    side: Side
    status: OrderStatus
    requested_quantity: Decimal
    executed_quantity: Decimal
    average_fill_price: Decimal | None
    reduce_only: bool
    observed_at: datetime
    raw_response_sha256: str
    reason_code: str | None = None

    def validation_errors(self, request: ExecutionOrderRequestV1) -> tuple[str, ...]:
        errors: list[str] = []
        if self.venue_id != request.venue_id:
            errors.append("RESPONSE_VENUE_MISMATCH")
        if self.market_type != request.market_type:
            errors.append("RESPONSE_MARKET_TYPE_MISMATCH")
        if self.venue_symbol != request.venue_symbol:
            errors.append("RESPONSE_SYMBOL_MISMATCH")
        if self.client_order_id != request.client_order_id:
            errors.append("RESPONSE_CLIENT_ORDER_ID_MISMATCH")
        if self.side != request.side:
            errors.append("RESPONSE_SIDE_MISMATCH")
        if self.status not in ("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"):
            errors.append("RESPONSE_STATUS_INVALID")
        requested = _positive_decimal(self.requested_quantity)
        if requested is None or requested != _positive_decimal(request.quantity):
            errors.append("RESPONSE_REQUESTED_QUANTITY_MISMATCH")
        executed = Decimal(str(self.executed_quantity)) if not isinstance(self.executed_quantity, bool) else Decimal("-1")
        if not executed.is_finite() or executed < 0:
            errors.append("RESPONSE_EXECUTED_QUANTITY_INVALID")
        elif requested is not None and executed > requested:
            errors.append("RESPONSE_OVERFILL_DETECTED")
        if self.status == "PARTIALLY_FILLED" and (executed <= 0 or (requested is not None and executed >= requested)):
            errors.append("PARTIAL_FILL_QUANTITY_INCONSISTENT")
        if self.status == "FILLED" and requested is not None and executed != requested:
            errors.append("FILLED_QUANTITY_INCONSISTENT")
        if self.status in ("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED") and not (
            isinstance(self.venue_order_id, str) and self.venue_order_id.strip()
        ):
            errors.append("VENUE_ORDER_ID_MISSING")
        if self.reduce_only is not request.reduce_only:
            errors.append("RESPONSE_REDUCE_ONLY_MISMATCH")
        if not _aware(self.observed_at):
            errors.append("RESPONSE_TIMESTAMP_NOT_TIMEZONE_AWARE")
        if not _sha256(self.raw_response_sha256):
            errors.append("RAW_RESPONSE_HASH_INVALID")
        if self.average_fill_price is not None and _positive_decimal(self.average_fill_price) is None:
            errors.append("AVERAGE_FILL_PRICE_INVALID")
        if executed > 0 and self.average_fill_price is None:
            errors.append("FILL_PRICE_MISSING")
        return tuple(dict.fromkeys(errors))


@dataclass(frozen=True)
class PositionSnapshotV1:
    venue_id: str
    market_type: MarketType
    venue_symbol: str
    position_quantity: Decimal
    observed_at: datetime
    raw_response_sha256: str


@dataclass(frozen=True)
class AccountReconciliationSnapshotV1:
    venue_id: str
    market_type: MarketType
    observed_at: datetime
    open_order_ids: tuple[str, ...]
    position_snapshot_sha256: str
    raw_response_sha256: str
    reconciliation_ref: str


@runtime_checkable
class ExecutionAdapterV1(Protocol):
    """Venue adapter interface. Implementations must not retry ambiguous submits."""

    def capabilities(self) -> ExecutionAdapterCapabilitiesV1: ...

    def submit_order(self, *, request: ExecutionOrderRequestV1) -> VenueOrderSnapshotV1:
        """Submit once; timeout/ambiguous response must become UNKNOWN, never auto-retry."""
        ...

    def get_order(
        self, *, client_order_id: str, venue_order_id: str | None = None
    ) -> VenueOrderSnapshotV1 | None: ...

    def cancel_order(
        self, *, client_order_id: str, venue_order_id: str | None = None
    ) -> VenueOrderSnapshotV1: ...

    def get_open_orders(self, *, venue_symbol: str) -> tuple[VenueOrderSnapshotV1, ...]: ...

    def get_positions(self, *, venue_symbol: str) -> tuple[PositionSnapshotV1, ...]: ...

    def reconcile_account(self) -> AccountReconciliationSnapshotV1: ...


def validate_adapter_readiness(
    capabilities: ExecutionAdapterCapabilitiesV1,
    *,
    expected_venue_id: str,
    expected_market_type: MarketType,
) -> tuple[str, ...]:
    """Return blockers; an unverified adapter is never ready for live execution."""
    errors = list(capabilities.validation_errors())
    if capabilities.venue_id != expected_venue_id:
        errors.append("CAPABILITY_VENUE_SCOPE_MISMATCH")
    if capabilities.market_type != expected_market_type:
        errors.append("CAPABILITY_MARKET_TYPE_SCOPE_MISMATCH")
    return tuple(dict.fromkeys(errors))
