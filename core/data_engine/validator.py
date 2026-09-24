"""
Mother Agent - Raw Data Validator
Data Engine v1.0
"""

from datetime import datetime
import math
from typing import Dict, Iterable, List


REQUIRED_COLUMNS = {
    "symbol",
    "price",
    "amount",
    "side",
    "updated",
    "sequence",
}


class RawDataValidator:
    """
    Validates the structural integrity of raw trade rows.

    This validator does not modify Raw Data.
    """

    def validate_row(self, row: Dict[str, str]) -> List[str]:
        """
        Validate one raw trade row.

        Returns:
            A list of validation errors.
            An empty list means the row is valid.
        """

        errors = []

        missing_columns = REQUIRED_COLUMNS - set(row.keys())

        if missing_columns:
            errors.append(
                f"Missing columns: {sorted(missing_columns)}"
            )
            return errors

        if not row.get("symbol"):
            errors.append("Empty symbol")

        if not row.get("price"):
            errors.append("Empty price")

        if not row.get("amount"):
            errors.append("Empty amount")

        if not row.get("side"):
            errors.append("Empty side")

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
            int(row["sequence"])
        except (ValueError, TypeError):
            errors.append("Invalid sequence")

        try:
            normalized_timestamp = row["updated"]
            if normalized_timestamp.endswith("Z"):
                normalized_timestamp = normalized_timestamp[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(normalized_timestamp)
            if timestamp.tzinfo is None:
                errors.append("Timestamp must be timezone-aware")
        except (ValueError, TypeError, AttributeError):
            errors.append("Invalid timestamp")

        return errors

    def validate_rows(
        self,
        rows: Iterable[Dict[str, str]],
    ) -> Dict[str, int]:
        """
        Validate multiple raw trade rows.

        Returns summary statistics only.
        """

        total_rows = 0
        valid_rows = 0
        invalid_rows = 0

        for row in rows:
            total_rows += 1

            errors = self.validate_row(row)

            if errors:
                invalid_rows += 1
            else:
                valid_rows += 1

        return {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
        }
