"""Desktop interface for the expense ledger."""

import argparse
import logging
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import default_config_path, load_config
from .errors import ExpenseManagerError, ValidationError
from .models import Transaction
from .service import ExpenseService
from .storage import ExpenseRepository
from .validation import parse_date

LOGGER = logging.getLogger(__name__)


def _format_money(amount_cents: int) -> str:
    return f"{amount_cents // 100}.{amount_cents % 100:02d}"


def _optional_date(value: str, field: str) -> date | None:
    normalized = value.strip()
    return parse_date(normalized, field) if normalized else None


class ExpenseManagerWindow:
    """Tkinter window for recording and reviewing expenses."""

    def __init__(self, root: tk.Tk, service: ExpenseService):
        self.root = root
        self.service = service
        self.root.title("Expense Manager")
        self.root.geometry("1080x760")
        self.root.minsize(800, 560)

        self.start_filter = tk.StringVar()
        self.end_filter = tk.StringVar()
        self.category_filter = tk.StringVar(value="All categories")
        self.date_value = tk.StringVar(value=date.today().isoformat())
        self.description_value = tk.StringVar()
        self.category_value = tk.StringVar()
        self.amount_value = tk.StringVar()
        self.status_value = tk.StringVar(value="Ready")
        self._transactions_by_id: dict[str, Transaction] = {}

        self._configure_styles()
        self._build_layout()
        self.refresh()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(background="#F2F5F2")
        style.configure("App.TFrame", background="#F2F5F2")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#F2F5F2", foreground="#1F302C", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#F2F5F2", foreground="#1F302C", font=("Segoe UI", 24, "bold"))
        style.configure("Subtitle.TLabel", background="#F2F5F2", foreground="#65746F", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#FFFFFF", foreground="#65746F", font=("Segoe UI", 9, "bold"))
        style.configure("Metric.TLabel", background="#FFFFFF", foreground="#1F302C", font=("Segoe UI", 20, "bold"))
        style.configure("MetricDetail.TLabel", background="#FFFFFF", foreground="#65746F", font=("Segoe UI", 9))
        style.configure("TLabelframe", background="#FFFFFF", bordercolor="#D9E2DD", relief="solid")
        style.configure("TLabelframe.Label", background="#FFFFFF", foreground="#1F302C", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#FFFFFF", foreground="#1F302C", padding=7)
        style.configure("TCombobox", fieldbackground="#FFFFFF", foreground="#1F302C", padding=6)
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(12, 8), background="#E8EEEA", foreground="#1F302C", borderwidth=0)
        style.map("TButton", background=[("active", "#DCE6E0"), ("pressed", "#D1DED6")])
        style.configure("Accent.TButton", background="#C1E1D9", foreground="#FFFFFF")
        style.map("Accent.TButton", background=[("active", "#196A56"), ("pressed", "#155B49")])
        style.configure("Danger.TButton", background="#F4E9E5", foreground="#9A4936")
        style.map("Danger.TButton", background=[("active", "#EEDBD4"), ("pressed", "#E8CEC4")])
        style.configure(
            "Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#253631",
            rowheight=36,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#EAF0EC",
            foreground="#52645D",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 9),
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", "#D9ECE4")], foreground=[("selected", "#1F302C")])

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=24, style="App.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        ttk.Label(outer, text="Expenses", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="A clear view of what you spend.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 18))

        filters = ttk.LabelFrame(outer, text="FILTER TRANSACTIONS", padding=(14, 12), style="TLabelframe")
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        filters.columnconfigure(7, weight=1)
        ttk.Label(filters, text="From").grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(filters, textvariable=self.start_filter, width=13).grid(
            row=0, column=1, padx=(0, 12)
        )
        ttk.Label(filters, text="To").grid(row=0, column=2, padx=(0, 5))
        ttk.Entry(filters, textvariable=self.end_filter, width=13).grid(
            row=0, column=3, padx=(0, 12)
        )
        ttk.Label(filters, text="Category").grid(row=0, column=4, padx=(0, 5))
        self.category_combo = ttk.Combobox(
            filters,
            textvariable=self.category_filter,
            values=("All categories",),
            state="readonly",
            width=18,
        )
        self.category_combo.grid(row=0, column=5, padx=(0, 8))
        self.category_combo.bind("<<ComboboxSelected>>", lambda *_: self.refresh())
        ttk.Button(filters, text="Apply", command=self.refresh).grid(row=0, column=6)
        ttk.Button(filters, text="Clear", command=self._clear_filters).grid(
            row=0, column=7, sticky="e", padx=(8, 0)
        )

        metrics = ttk.Frame(outer, style="App.TFrame")
        metrics.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        for column in range(3):
            metrics.columnconfigure(column, weight=1, uniform="metric")
        total_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 13))
        total_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(total_card, text="TOTAL SPEND", style="CardTitle.TLabel").pack(anchor="w")
        self.summary_label = ttk.Label(total_card, text="0.00", style="Metric.TLabel")
        self.summary_label.pack(anchor="w", pady=(5, 0))
        count_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 13))
        count_card.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(count_card, text="TRANSACTIONS", style="CardTitle.TLabel").pack(anchor="w")
        self.transaction_count_label = ttk.Label(count_card, text="0", style="Metric.TLabel")
        self.transaction_count_label.pack(anchor="w", pady=(5, 0))
        category_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 13))
        category_card.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        ttk.Label(category_card, text="CATEGORIES", style="CardTitle.TLabel").pack(anchor="w")
        self.category_count_label = ttk.Label(category_card, text="0", style="Metric.TLabel")
        self.category_count_label.pack(anchor="w", pady=(5, 0))

        ttk.Label(outer, text="Transactions", font=("Segoe UI", 13, "bold")).grid(
            row=4, column=0, sticky="w", pady=(0, 8)
        )
        table_frame = ttk.Frame(outer)
        table_frame.grid(row=5, column=0, sticky="nsew", pady=(0, 14))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(
            table_frame,
            columns=("date", "category", "description", "amount"),
            show="headings",
            selectmode="browse",
        )
        for column, heading, width in (
            ("date", "Date", 120),
            ("category", "Category", 150),
            ("description", "Description", 500),
            ("amount", "Amount", 120),
        ):
            self.table.heading(column, text=heading)
            self.table.column(column, width=width, minwidth=80, anchor="w")
        self.table.column("amount", anchor="e")
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.tag_configure("even", background="#FFFFFF")
        self.table.tag_configure("odd", background="#F7F9F7")
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        add_frame = ttk.LabelFrame(outer, text="ADD EXPENSE", padding=(14, 12), style="TLabelframe")
        add_frame.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        add_frame.columnconfigure(3, weight=1)
        add_frame.columnconfigure(6, weight=1)
        ttk.Label(add_frame, text="Date").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(add_frame, textvariable=self.date_value, width=12).grid(
            row=0, column=1, sticky="ew", padx=(0, 10)
        )
        ttk.Label(add_frame, text="Description").grid(row=0, column=2, sticky="w", padx=(0, 5))
        description_entry = ttk.Entry(add_frame, textvariable=self.description_value)
        description_entry.grid(row=0, column=3, columnspan=4, sticky="ew")
        ttk.Label(add_frame, text="Category").grid(row=1, column=0, sticky="w", padx=(0, 7), pady=(10, 0))
        ttk.Entry(add_frame, textvariable=self.category_value, width=18).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(10, 0)
        )
        ttk.Label(add_frame, text="Amount").grid(row=1, column=3, sticky="w", padx=(0, 7), pady=(10, 0))
        ttk.Entry(add_frame, textvariable=self.amount_value, width=14).grid(
            row=1, column=4, columnspan=2, sticky="ew", padx=(0, 14), pady=(10, 0)
        )
        ttk.Button(add_frame, text="Add expense", style="Accent.TButton", command=self._add_expense).grid(
            row=1, column=6, sticky="ew", pady=(10, 0)
        )

        actions = ttk.Frame(outer)
        actions.grid(row=7, column=0, sticky="ew")
        ttk.Button(actions, text="Delete selected", style="Danger.TButton", command=self._delete_selected).pack(
            side=tk.LEFT
        )
        ttk.Button(actions, text="Import CSV", command=self._import_csv).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(actions, text="Export CSV", command=self._export_csv).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side=tk.RIGHT)
        ttk.Label(outer, textvariable=self.status_value, style="Subtitle.TLabel", anchor="w").grid(
            row=8, column=0, sticky="ew", pady=(12, 0)
        )
        description_entry.focus_set()

    def _date_range(self) -> tuple[date | None, date | None]:
        start = _optional_date(self.start_filter.get(), "start date")
        end = _optional_date(self.end_filter.get(), "end date")
        if start is not None and end is not None and start > end:
            raise ValidationError("start date cannot be later than end date.")
        return start, end

    def _clear_filters(self) -> None:
        self.start_filter.set("")
        self.end_filter.set("")
        self.category_filter.set("All categories")
        self.refresh()

    def refresh(self) -> None:
        try:
            start, end = self._date_range()
            selected_category = self.category_filter.get()
            category = selected_category if selected_category != "All categories" else None
            transactions = self.service.list_transactions(start, end, category)
            summaries = self.service.summarize(start, end)
        except (ExpenseManagerError, ValueError) as exc:
            messagebox.showerror("Could not refresh expenses", str(exc), parent=self.root)
            return

        self._transactions_by_id.clear()
        for item in self.table.get_children():
            self.table.delete(item)
        for index, transaction in enumerate(transactions):
            row_id = str(transaction.id)
            self._transactions_by_id[row_id] = transaction
            self.table.insert(
                "",
                tk.END,
                iid=row_id,
                values=(
                    transaction.date.isoformat(),
                    transaction.category,
                    transaction.description,
                    _format_money(transaction.amount_cents),
                ),
                tags=("even" if index % 2 == 0 else "odd",),
            )

        known_categories = sorted({category_name for category_name, _, _ in summaries}, key=str.casefold)
        categories = ["All categories", *known_categories]
        self.category_combo.configure(values=categories)
        if selected_category not in categories:
            self.category_filter.set("All categories")
        total_cents = sum(transaction.amount_cents for transaction in transactions)
        transaction_count = len(transactions)
        self.summary_label.configure(text=_format_money(total_cents))
        self.transaction_count_label.configure(text=str(transaction_count))
        self.category_count_label.configure(
            text=str(len({transaction.category for transaction in transactions}))
        )
        self.status_value.set(f"Showing {len(transactions)} expense(s)")

    def _add_expense(self) -> None:
        try:
            transaction = self.service.add(
                self.date_value.get(),
                self.description_value.get(),
                self.category_value.get(),
                self.amount_value.get(),
            )
        except ExpenseManagerError as exc:
            messagebox.showerror("Could not add expense", str(exc), parent=self.root)
            return
        self.description_value.set("")
        self.category_value.set("")
        self.amount_value.set("")
        self.start_filter.set("")
        self.end_filter.set("")
        self.category_filter.set("All categories")
        self.refresh()
        self.status_value.set(f"Added expense #{transaction.id}")

    def _delete_selected(self) -> None:
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo(
                "Select an expense", "Select an expense row to delete.", parent=self.root
            )
            return
        transaction = self._transactions_by_id[selection[0]]
        if not messagebox.askyesno(
            "Delete expense",
            f"Delete '{transaction.description}' ({_format_money(transaction.amount_cents)})?",
            parent=self.root,
        ):
            return
        try:
            self.service.delete(transaction.id or 0)
        except ExpenseManagerError as exc:
            messagebox.showerror("Could not delete expense", str(exc), parent=self.root)
            return
        self.status_value.set(f"Deleted expense #{transaction.id}")
        self.refresh()

    def _import_csv(self) -> None:
        selected_path = filedialog.askopenfilename(
            parent=self.root,
            title="Import expenses from CSV",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not selected_path:
            return
        try:
            count = self.service.import_csv(Path(selected_path))
        except ExpenseManagerError as exc:
            messagebox.showerror("Could not import CSV", str(exc), parent=self.root)
            return
        self.status_value.set(f"Imported {count} expense(s)")
        self.refresh()

    def _export_csv(self) -> None:
        selected_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export expenses to CSV",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not selected_path:
            return
        try:
            start, end = self._date_range()
            selected_category = self.category_filter.get()
            category = selected_category if selected_category != "All categories" else None
            transactions = self.service.list_transactions(start, end, category)
            count = self.service.export_csv(Path(selected_path), transactions)
        except (ExpenseManagerError, ValueError) as exc:
            messagebox.showerror("Could not export CSV", str(exc), parent=self.root)
            return
        self.status_value.set(f"Exported {count} expense(s) to {selected_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the Expense Manager desktop interface.")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="JSON configuration file (default: ~/.expense_manager/config.json)",
    )
    arguments = parser.parse_args(argv)
    try:
        config = load_config(arguments.config)
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        service = ExpenseService(ExpenseRepository(config.database_path))
        root = tk.Tk()
        ExpenseManagerWindow(root, service)
        root.mainloop()
        return 0
    except ExpenseManagerError as exc:
        LOGGER.error("%s", exc)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except tk.TclError as exc:
        LOGGER.error("Could not start the desktop interface: %s", exc)
        parser.exit(2, f"{parser.prog}: error: could not start the desktop interface: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
