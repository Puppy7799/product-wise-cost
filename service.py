"""Expense operations and CSV interchange."""

import csv
import logging
import os
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from .errors import DataFileError, ValidationError
from .models import Transaction
from .storage import ExpenseRepository
from .validation import (
    parse_amount,
    parse_date,
    validate_date_range,
    validate_text,
)

LOGGER = logging.getLogger(__name__)
CSV_FIELDS = ("date", "description", "category", "amount")


class ExpenseService:
    """Validate expense data and coordinate storage and CSV operations."""

    def __init__(self, repository: ExpenseRepository):
        self.repository = repository

    def add(
        self, transaction_date: str, description: str, category: str, amount: str
    ) -> Transaction:
        transaction = self._build_transaction(
            transaction_date, description, category, amount
        )
        transaction_id = self.repository.add_many([transaction])[0]
        LOGGER.info("Added expense in category '%s'.", transaction.category)
        return replace(transaction, id=transaction_id)

    def list_transactions(
        self,
        start: date | None = None,
        end: date | None = None,
        category: str | None = None,
    ) -> list[Transaction]:
        validate_date_range(start, end)
        normalized_category = (
            validate_text(category, "category", 60) if category is not None else None
        )
        return self.repository.list_transactions(start, end, normalized_category)

    def summarize(
        self, start: date | None = None, end: date | None = None
    ) -> list[tuple[str, int, int]]:
        validate_date_range(start, end)
        return self.repository.summarize(start, end)

    def delete(self, transaction_id: int) -> bool:
        if transaction_id <= 0:
            raise ValidationError("transaction ID must be a positive integer.")
        deleted = self.repository.delete(transaction_id)
        if deleted:
            LOGGER.info("Deleted transaction %s.", transaction_id)
        return deleted

    def import_csv(self, path: Path) -> int:
        transactions: list[Transaction] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames is None:
                    raise DataFileError("CSV file is empty or has no header row.")
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise DataFileError("CSV contains duplicate column names.")
                missing = set(CSV_FIELDS) - set(reader.fieldnames)
                if missing:
                    raise DataFileError(
                        f"CSV is missing required column(s): {', '.join(sorted(missing))}."
                    )
                for row_number, row in enumerate(reader, start=2):
                    if None in row or any(row.get(field) is None for field in CSV_FIELDS):
                        raise DataFileError(f"CSV row {row_number} has an invalid number of columns.")
                    try:
                        transactions.append(
                            self._build_transaction(
                                row["date"], row["description"], row["category"], row["amount"]
                            )
                        )
                    except ValidationError as exc:
                        raise DataFileError(f"CSV row {row_number}: {exc}") from exc
        except DataFileError:
            raise
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise DataFileError(f"Could not read CSV file '{path}': {exc}") from exc

        if not transactions:
            raise DataFileError("CSV file contains no transactions.")
        self.repository.add_many(transactions)
        LOGGER.info("Imported %s transactions from '%s'.", len(transactions), path)
        return len(transactions)

    def export_csv(self, path: Path, transactions: list[Transaction]) -> int:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=path.parent or Path("."),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                writer = csv.DictWriter(destination, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for transaction in transactions:
                    writer.writerow(
                        {
                            "date": transaction.date.isoformat(),
                            "description": transaction.description,
                            "category": transaction.category,
                            "amount": (
                                f"{transaction.amount_cents // 100}."
                                f"{transaction.amount_cents % 100:02d}"
                            ),
                        }
                    )
            os.replace(temporary_path, path)
        except (OSError, csv.Error) as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise DataFileError(f"Could not write CSV file '{path}': {exc}") from exc
        LOGGER.info("Exported %s transactions to '%s'.", len(transactions), path)
        return len(transactions)

    @staticmethod
    def _build_transaction(
        transaction_date: str, description: str, category: str, amount: str
    ) -> Transaction:
        return Transaction(
            id=None,
            date=parse_date(transaction_date),
            description=validate_text(description, "description", 200),
            category=validate_text(category, "category", 60),
            amount_cents=parse_amount(amount),
        )
