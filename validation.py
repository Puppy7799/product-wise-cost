"""Input validation and normalization."""

from datetime import date
from decimal import Decimal, InvalidOperation

from .errors import ValidationError


def validate_text(value: str, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field} cannot be empty.")
    if len(normalized) > max_length:
        raise ValidationError(f"{field} cannot exceed {max_length} characters.")
    return normalized


def parse_date(value: str, field: str = "date") -> date:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must use YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError(f"{field} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value.strip():
        raise ValidationError(f"{field} must use YYYY-MM-DD format.")
    return parsed


def parse_amount(value: str | Decimal) -> int:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValidationError("amount must be a positive number with at most 2 decimal places.") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValidationError("amount must be a positive number with at most 2 decimal places.")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValidationError("amount must be a positive number with at most 2 decimal places.")
    return int(cents)


def validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise ValidationError("start date cannot be later than end date.")
