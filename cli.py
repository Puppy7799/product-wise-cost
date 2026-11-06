"""Command-line interface for the expense ledger."""

import argparse
import logging
from datetime import date
from pathlib import Path

from .config import default_config_path, load_config, write_default_config
from .errors import ExpenseManagerError, ValidationError
from .service import ExpenseService
from .storage import ExpenseRepository
from .validation import parse_date

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense-manager",
        description="Record, search, summarize, and exchange personal expenses.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="JSON configuration file (default: ~/.expense_manager/config.json)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_config = commands.add_parser("init-config", help="create a starter JSON configuration")
    init_config.add_argument("--force", action="store_true", help="replace an existing configuration")

    add = commands.add_parser("add", help="record an expense")
    add.add_argument("--date", default=date.today().isoformat(), help="expense date (YYYY-MM-DD)")
    add.add_argument("--description", required=True, help="what the expense was for")
    add.add_argument("--category", required=True, help="expense category")
    add.add_argument("--amount", required=True, help="positive amount with up to 2 decimals")

    listing = commands.add_parser("list", help="list recorded expenses")
    _add_date_filters(listing)
    listing.add_argument("--category", help="filter by exact category")

    summary = commands.add_parser("summary", help="summarize expenses by category")
    _add_date_filters(summary)

    delete = commands.add_parser("delete", help="delete an expense by ID")
    delete.add_argument("id", type=int, help="transaction ID shown by the list command")

    import_csv = commands.add_parser("import-csv", help="import a CSV file")
    import_csv.add_argument("path", type=Path, help="CSV file with date,description,category,amount columns")

    export_csv = commands.add_parser("export-csv", help="export expenses to CSV")
    export_csv.add_argument("path", type=Path, help="destination CSV file")
    _add_date_filters(export_csv)
    return parser


def _add_date_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", help="include expenses on or after YYYY-MM-DD")
    parser.add_argument("--end", help="include expenses on or before YYYY-MM-DD")


def _date_filters(arguments: argparse.Namespace) -> tuple[date | None, date | None]:
    start = parse_date(arguments.start, "start date") if arguments.start else None
    end = parse_date(arguments.end, "end date") if arguments.end else None
    return start, end


def _format_money(amount_cents: int) -> str:
    return f"{amount_cents // 100}.{amount_cents % 100:02d}"


def _run(arguments: argparse.Namespace) -> int:
    if arguments.command == "init-config":
        write_default_config(arguments.config, arguments.force)
        print(f"Configuration created at {arguments.config.expanduser()}")
        return 0

    config = load_config(arguments.config)
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    service = ExpenseService(ExpenseRepository(config.database_path))

    if arguments.command == "add":
        transaction = service.add(
            arguments.date, arguments.description, arguments.category, arguments.amount
        )
        print(
            f"Added {transaction.date.isoformat()} {transaction.category}: "
            f"{_format_money(transaction.amount_cents)}"
        )
    elif arguments.command == "list":
        start, end = _date_filters(arguments)
        transactions = service.list_transactions(start, end, arguments.category)
        if not transactions:
            print("No expenses found.")
        else:
            for item in transactions:
                print(
                    f"{item.id}\t{item.date.isoformat()}\t{item.category}\t"
                    f"{_format_money(item.amount_cents)}\t{item.description}"
                )
    elif arguments.command == "summary":
        start, end = _date_filters(arguments)
        summaries = service.summarize(start, end)
        if not summaries:
            print("No expenses found.")
        else:
            total_cents = sum(amount for _, _, amount in summaries)
            for category, count, amount in summaries:
                print(f"{category}\t{count} transaction(s)\t{_format_money(amount)}")
            print(f"TOTAL\t{sum(count for _, count, _ in summaries)} transaction(s)\t{_format_money(total_cents)}")
    elif arguments.command == "delete":
        if not service.delete(arguments.id):
            raise ValidationError(f"transaction {arguments.id} was not found.")
        print(f"Deleted transaction {arguments.id}.")
    elif arguments.command == "import-csv":
        count = service.import_csv(arguments.path)
        print(f"Imported {count} transaction(s).")
    elif arguments.command == "export-csv":
        start, end = _date_filters(arguments)
        transactions = service.list_transactions(start, end)
        count = service.export_csv(arguments.path, transactions)
        print(f"Exported {count} transaction(s) to {arguments.path}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        return _run(arguments)
    except ExpenseManagerError as exc:
        LOGGER.error("%s", exc)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
