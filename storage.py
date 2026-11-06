"""SQLite persistence for expense transactions."""

import sqlite3
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from .errors import StorageError
from .models import Transaction


class ExpenseRepository:
    """Persist and query transactions in a local SQLite database."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.database_path)
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise StorageError(f"Database operation failed: {exc}") from exc
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def _initialize(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY,
                        date TEXT NOT NULL,
                        description TEXT NOT NULL,
                        category TEXT NOT NULL,
                        amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS transactions_date_idx ON transactions(date)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS transactions_category_idx ON transactions(category)"
                )
        except OSError as exc:
            raise StorageError(
                f"Cannot create database directory '{self.database_path.parent}': {exc}"
            ) from exc

    def add_many(self, transactions: list[Transaction]) -> list[int]:
        if not transactions:
            return []
        transaction_ids: list[int] = []
        try:
            with self._connection() as connection:
                for item in transactions:
                    cursor = connection.execute(
                        """
                        INSERT INTO transactions (date, description, category, amount_cents)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            item.date.isoformat(),
                            item.description,
                            item.category,
                            item.amount_cents,
                        ),
                    )
                    if cursor.lastrowid is None:
                        raise StorageError("Database did not return an ID for a saved transaction.")
                    transaction_ids.append(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise StorageError(f"Could not save transactions: {exc}") from exc
        return transaction_ids

    def list_transactions(
        self,
        start: date | None = None,
        end: date | None = None,
        category: str | None = None,
    ) -> list[Transaction]:
        clauses: list[str] = []
        parameters: list[str] = []
        if start is not None:
            clauses.append("date >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("date <= ?")
            parameters.append(end.isoformat())
        if category is not None:
            clauses.append("category = ?")
            parameters.append(category)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with closing(sqlite3.connect(self.database_path)) as connection:
                rows = connection.execute(
                    f"""
                    SELECT id, date, description, category, amount_cents
                    FROM transactions{where}
                    ORDER BY date DESC, id DESC
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not read transactions: {exc}") from exc
        return [
            Transaction(
                id=row[0],
                date=date.fromisoformat(row[1]),
                description=row[2],
                category=row[3],
                amount_cents=row[4],
            )
            for row in rows
        ]

    def summarize(
        self, start: date | None = None, end: date | None = None
    ) -> list[tuple[str, int, int]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if start is not None:
            clauses.append("date >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("date <= ?")
            parameters.append(end.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with closing(sqlite3.connect(self.database_path)) as connection:
                rows = connection.execute(
                    f"""
                    SELECT category, COUNT(*), SUM(amount_cents)
                    FROM transactions{where}
                    GROUP BY category
                    ORDER BY category COLLATE NOCASE
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not summarize transactions: {exc}") from exc
        return [(row[0], row[1], row[2]) for row in rows]

    def delete(self, transaction_id: int) -> bool:
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "DELETE FROM transactions WHERE id = ?", (transaction_id,)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise StorageError(f"Could not delete transaction: {exc}") from exc
