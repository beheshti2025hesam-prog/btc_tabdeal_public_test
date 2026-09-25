"""
HES Trade Agent - Raw Data Validator.
"""
from datetime import datetime
import math
from typing import Dict, Iterable, List

REQUIRED_COLUMNS = {"symbol", "price", "amount", "side", "updated", "sequence"}
VALID_SIDES = {"buy", "sell"}

class RawDataValidator:
    """Validate raw trade structure and hard boundaries without mutation."""
    def validate_row(self, row: Dict[str, str]) -> List[str]:
        errors = []
        missing = REQUIRED_COLUMNS - set(row.keys())
        if missing:
            return [f"Missing columns: {sorted(missing)}"]
        if not row.get("symbol") or not row["symbol"].strip():
            errors.append("Empty symbol")
        if not row.get("price"):
            errors.append("Empty price")
        if not row.get("amount"):
            errors.append("Empty amount")
        if not row.get("side") or not row["side"].strip():
            errors.append("Empty side")
        elif row["side"].strip().lower() not in VALID_SIDES:
            errors.append("Invalid side")
        if not row.get("updated"):
            errors.append("Empty updated timestamp")
        if not row.get("sequence"):
            errors.append("Empty sequence")
        try:
            price = float(row["price"])
            if not math.isfinite(price) or price <= 0:
                errors.append("Invalid price")
        except (ValueError, TypeError):
            errors.append("Invalid price")
        try:
            amount = float(row["amount"])
            if not math.isfinite(amount) or amount <= 0:
                errors.append("Invalid amount")
        except (ValueError, TypeError):
            errors.append("Invalid amount")
        try:
            sequence = int(row["sequence"])
            if sequence <= 0:
                errors.append("Invalid sequence")
        except (ValueError, TypeError):
            errors.append("Invalid sequence")
        try:
            value = row["updated"]
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is None:
                errors.append("Timestamp must be timezone-aware")
        except (ValueError, TypeError, AttributeError):
            errors.append("Invalid timestamp")
        return errors

    def validate_rows(self, rows: Iterable[Dict[str, str]]) -> Dict[str, int]:
        total = valid = invalid = 0
        for row in rows:
            total += 1
            if self.validate_row(row):
                invalid += 1
            else:
                valid += 1
        return {"total_rows": total, "valid_rows": valid, "invalid_rows": invalid}
