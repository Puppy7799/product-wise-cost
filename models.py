"""Data models used by the expense ledger."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Transaction:
    id: int | None
    date: date
    description: str
    category: str
    amount_cents: int
