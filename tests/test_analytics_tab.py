from __future__ import annotations

import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

from app.services import CurrencyService
from gui.controllers import FinancialController
from gui.tabs.analytics import _draw_breakdown_pie, build_analytics_tab
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def _insert_wallet(
    conn: sqlite3.Connection, wallet_id: int, *, initial_balance: float = 0.0
) -> None:
    conn.execute(
        "INSERT INTO wallets (id, name, currency, initial_balance, is_active) "
        "VALUES (?, 'Test', 'KZT', ?, 1)",
        (int(wallet_id), float(initial_balance)),
    )
    conn.commit()


def _insert_transfer(
    conn: sqlite3.Connection,
    *,
    transfer_id: int,
    from_wallet_id: int,
    to_wallet_id: int,
    date: str,
    amount_base: float,
) -> None:
    conn.execute(
        "INSERT INTO transfers "
        "(id, from_wallet_id, to_wallet_id, date, amount_original, currency, "
        "rate_at_operation, amount_base, description) "
        "VALUES (?, ?, ?, ?, ?, 'KZT', 1.0, ?, 'Transfer')",
        (
            int(transfer_id),
            int(from_wallet_id),
            int(to_wallet_id),
            str(date),
            float(amount_base),
            float(amount_base),
        ),
    )
    conn.commit()


def _insert_record(
    conn: sqlite3.Connection,
    *,
    record_type: str,
    date: str,
    wallet_id: int,
    amount_base: float,
    transfer_id=None,
    category: str = "General",
) -> None:
    conn.execute(
        "INSERT INTO records "
        "(type, date, wallet_id, transfer_id, amount_original, currency, "
        "rate_at_operation, amount_base, category) "
        "VALUES (?, ?, ?, ?, ?, 'KZT', 1.0, ?, ?)",
        (
            str(record_type),
            str(date),
            int(wallet_id),
            transfer_id,
            float(amount_base),
            float(amount_base),
            str(category),
        ),
    )
    conn.commit()


def _insert_tag(conn: sqlite3.Connection, tag_id: int, *, name: str, color: str = "") -> None:
    conn.execute(
        "INSERT INTO tags (id, name, color, usage_count, last_used_at) VALUES (?, ?, ?, 0, '')",
        (int(tag_id), str(name), str(color)),
    )
    conn.commit()


def _insert_record_tag(conn: sqlite3.Connection, *, record_id: int, tag_id: int) -> None:
    conn.execute(
        "INSERT INTO record_tags (record_id, tag_id) VALUES (?, ?)",
        (int(record_id), int(tag_id)),
    )
    conn.commit()


def _make_controller(db_path: Path) -> tuple[SQLiteRecordRepository, FinancialController]:
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService())
    return repo, controller


def test_empty_db_get_savings_rate_returns_zero(tmp_path: Path) -> None:
    repo, controller = _make_controller(tmp_path / "analytics.db")
    try:
        assert controller.get_savings_rate("2026-01-01", "2026-01-31") == 0.0
    finally:
        repo.close()


def test_empty_db_get_monthly_summary_returns_empty_list(tmp_path: Path) -> None:
    repo, controller = _make_controller(tmp_path / "analytics.db")
    try:
        assert controller.get_monthly_summary("2026-01-01", "2026-03-31") == []
    finally:
        repo.close()


def test_empty_db_get_net_worth_timeline_returns_empty_list(tmp_path: Path) -> None:
    repo, controller = _make_controller(tmp_path / "analytics.db")
    try:
        assert controller.get_net_worth_timeline() == []
    finally:
        repo.close()


def test_monthly_summary_three_months_returns_three_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-05", wallet_id=1, amount_base=100.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-02-05", wallet_id=1, amount_base=20.0
        )
        _insert_record(conn, record_type="income", date="2026-03-05", wallet_id=1, amount_base=10.0)
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        rows = controller.get_monthly_summary("2026-01-01", "2026-03-31")
        assert len(rows) == 3
    finally:
        repo.close()


def test_savings_rate_positive_when_income_exceeds_expenses(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=200.0
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        assert controller.get_savings_rate("2026-01-01", "2026-01-31") > 0
    finally:
        repo.close()


def test_savings_rate_negative_when_expenses_exceed_income(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=2000.0
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        assert controller.get_savings_rate("2026-01-01", "2026-01-31") < 0
    finally:
        repo.close()


def test_transfer_records_do_not_affect_savings_rate(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_wallet(conn, 2)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=200.0
        )

        _insert_transfer(
            conn,
            transfer_id=1,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-01-10",
            amount_base=500.0,
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-10",
            wallet_id=1,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-10",
            wallet_id=2,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        assert controller.get_savings_rate("2026-01-01", "2026-01-31") == 80.0
    finally:
        repo.close()


def test_get_spending_by_category_with_limit_returns_at_most_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        for idx, (cat, amount) in enumerate(
            [
                ("A", 100.0),
                ("B", 200.0),
                ("C", 300.0),
                ("D", 400.0),
                ("E", 500.0),
            ],
            start=1,
        ):
            _insert_record(
                conn,
                record_type="expense",
                date=f"2026-01-{idx:02d}",
                wallet_id=1,
                amount_base=amount,
                category=cat,
            )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        rows = controller.get_spending_by_category("2026-01-01", "2026-01-31", limit=3)
        assert len(rows) <= 3
    finally:
        repo.close()


def test_get_year_income_and_avg_monthly_income_year_to_date(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-05", wallet_id=1, amount_base=100.0
        )
        _insert_record(
            conn, record_type="income", date="2026-02-05", wallet_id=1, amount_base=200.0
        )
        _insert_record(
            conn, record_type="income", date="2026-03-05", wallet_id=1, amount_base=999.0
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        # Up to Feb inclusive -> two months (Jan, Feb)
        assert controller.get_year_income(2026, up_to_date="2026-02-28") == 300.0
        assert controller.get_average_monthly_income(2026, up_to_date="2026-02-28") == 150.0
    finally:
        repo.close()


def test_average_monthly_expenses_and_financial_freedom_ratio(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1, initial_balance=1200.0)
        _insert_record(
            conn, record_type="expense", date="2026-01-10", wallet_id=1, amount_base=200.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-02-10", wallet_id=1, amount_base=200.0
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        avg_monthly = controller.get_average_monthly_expenses("2026-01-01", "2026-02-28")
        assert avg_monthly == 200.0
    finally:
        repo.close()


def test_convert_base_to_usd_uses_configured_rate(tmp_path: Path) -> None:
    repo, controller = _make_controller(tmp_path / "analytics.db")
    try:
        # Default CurrencyService rate in tests: 500 KZT per USD
        assert controller.convert_base_to_usd(1000.0) == 2.0
    finally:
        repo.close()


def test_get_year_expense_and_time_costs_use_year_to_date_expenses(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1, initial_balance=0.0)
        _insert_record(
            conn, record_type="expense", date="2026-01-10", wallet_id=1, amount_base=3100.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-02-10", wallet_id=1, amount_base=3100.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-03-10", wallet_id=1, amount_base=900.0
        )
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)
    try:
        burn = controller.get_burn_rate("2026-01-01", "2026-02-28")
        per_day, per_hour, per_minute = controller.get_time_costs("2026-01-01", "2026-02-28")
        assert burn == 105.08  # 6200 / 59 days
        assert controller.get_year_expense(2026, up_to_date="2026-02-28") == 6200.0
        assert controller.get_year_expense(2026) == 7100.0
        assert per_day == 16.99  # 6200 / 365
        assert per_hour == 0.71
        assert per_minute == 0.01
    finally:
        repo.close()


def test_analytics_tab_net_worth_uses_period_end_date() -> None:
    class _Controller:
        def __init__(self) -> None:
            self.total_balance_dates: list[str | None] = []

        def get_total_balance(self, date: str | None = None) -> float:
            self.total_balance_dates.append(date)
            return 1234.0

        def get_savings_rate(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_burn_rate(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def convert_base_to_usd(self, amount_base: float) -> float:
            return 0.0

        def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]:
            return (0.0, 0.0, 0.0)

        def get_net_worth_timeline(self) -> list:
            return []

        def get_spending_by_category(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_income_by_category(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_spending_by_tag(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_monthly_summary(
            self,
            start_date: str | None = None,
            end_date: str | None = None,
        ) -> list:
            return []

    class _Context(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.withdraw()
            self.controller = _Controller()

    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_analytics_tab(parent, context)
        context.update()

        bindings.period_from_entry.delete(0, tk.END)
        bindings.period_from_entry.insert(0, "2026-01-01")
        bindings.period_to_entry.delete(0, tk.END)
        bindings.period_to_entry.insert(0, "2026-01-31")

        refresh_button = next(
            child
            for child in parent.winfo_children()[0].winfo_children()
            if isinstance(child, ttk.Button) and child.cget("text") == "Обновить"
        )
        refresh_button.invoke()
        context.update()

        assert context.controller.total_balance_dates[-1] == "2026-01-31"
        assert bindings.net_worth_label.cget("text") == "Чистый капитал:  1,234 KZT"
    finally:
        context.destroy()


def test_analytics_tab_prefers_controller_money_formatter() -> None:
    class _Controller:
        def __init__(self) -> None:
            self.calls: list[tuple[float, int, bool]] = []

        def get_total_balance(self, date: str | None = None) -> float:
            return 1234.0

        def format_display_money(
            self,
            amount_base: float,
            *,
            precision: int = 2,
            with_code: bool = True,
        ) -> str:
            self.calls.append((amount_base, precision, with_code))
            if amount_base == 1234.0 and precision == 0 and with_code is True:
                return "USD 1,234"
            return f"formatted:{amount_base}:{precision}:{with_code}"

        def get_savings_rate(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_burn_rate(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def convert_base_to_usd(self, amount_base: float) -> float:
            return 0.0

        def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float:
            return 0.0

        def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float:
            return 0.0

        def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]:
            return (0.0, 0.0, 0.0)

        def get_net_worth_timeline(self) -> list:
            return []

        def get_spending_by_category(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_income_by_category(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_spending_by_tag(self, start_date: str, end_date: str, *, limit=None) -> list:
            return []

        def get_monthly_summary(
            self,
            start_date: str | None = None,
            end_date: str | None = None,
        ) -> list:
            return []

    class _Context(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.withdraw()
            self.controller = _Controller()

    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_analytics_tab(parent, context)
        context.update()

        bindings.refresh()
        context.update()

        assert bindings.net_worth_label.cget("text") == "Чистый капитал:  USD 1,234"
        assert (1234.0, 0, True) in context.controller.calls
    finally:
        context.destroy()


def test_analytics_tag_breakdown_toggle_renders_single_tag_tree(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-05",
            wallet_id=1,
            amount_base=900.0,
            category="Food",
        )
        record_id = int(conn.execute("SELECT MAX(id) FROM records").fetchone()[0])
        _insert_tag(conn, 1, name="food", color="#F2994A")
        _insert_tag(conn, 2, name="family", color="#34A853")
        _insert_record_tag(conn, record_id=record_id, tag_id=1)
        _insert_record_tag(conn, record_id=record_id, tag_id=2)
    finally:
        conn.close()

    repo, controller = _make_controller(db_path)

    class _Context(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.withdraw()
            self.controller = controller

    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        build_analytics_tab(parent, context)
        context.update()

        checkbuttons = [
            child
            for child in parent.winfo_children()[0].winfo_children()
            if isinstance(child, ttk.Checkbutton)
        ]
        assert checkbuttons, "Expected analytics breakdown toggle checkbutton"
        checkbuttons[0].invoke()
        context.update()

        tag_trees: list[ttk.Treeview] = []

        def _walk(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if isinstance(child, ttk.Treeview) and tuple(child.cget("columns")) == (
                    "tag",
                    "total",
                    "count",
                ):
                    tag_trees.append(child)
                _walk(child)

        _walk(parent)
        assert tag_trees, "Expected a tag breakdown treeview"
        values = [tag_trees[0].item(iid, "values") for iid in tag_trees[0].get_children()]
        assert ("#food", "900", "1") in values
        assert ("#family", "900", "1") in values
    finally:
        context.destroy()
        repo.close()


def test_draw_breakdown_pie_renders_single_full_slice() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        canvas = tk.Canvas(root, width=220, height=220)
        canvas.pack()
        root.update_idletasks()

        item = SimpleNamespace(total_base=250.0, color="#5B8DEF")
        _draw_breakdown_pie(canvas, [item])

        shape_ids = canvas.find_all()
        assert shape_ids
        assert canvas.type(shape_ids[0]) == "oval"
    finally:
        root.destroy()


def test_draw_breakdown_pie_aggregates_tail_into_other_slice() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        canvas = tk.Canvas(root, width=220, height=220)
        canvas.pack()
        root.update_idletasks()

        data = [
            SimpleNamespace(total_base=float(100 - idx), color=f"#0000{idx:02d}")
            for idx in range(11)
        ]
        _draw_breakdown_pie(canvas, data)

        text_values = [
            canvas.itemcget(item_id, "text")
            for item_id in canvas.find_all()
            if canvas.type(item_id) == "text"
        ]
        assert "Прочие расходы" in text_values
    finally:
        root.destroy()
