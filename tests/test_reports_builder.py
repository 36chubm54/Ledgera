from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from gui.tabs.reports.builder import ReportsFrame
from gui.tabs.reports.contracts import ReportsTabContext
from gui.tabs.reports_tab import build_reports_tab


def _make_context():
    controller = SimpleNamespace(
        load_active_wallets=lambda: [],
        generate_report_for_wallet=lambda wallet_id=None: None,
        net_worth_fixed=lambda: 0.0,
        net_worth_current=lambda: 0.0,
        get_base_currency_code=lambda: "KZT",
        get_debts=lambda wallet_id=None: [],
        get_display_currency_code=lambda: "KZT",
        format_display_money=lambda amount, precision=2, with_code=True: f"{amount:.2f}",
        format_display_amount=lambda amount, precision=2: f"{amount:.2f}",
        list_tags=lambda: [],
    )
    return SimpleNamespace(
        controller=controller,
        currency=object(),
        _run_background=MagicMock(),
    )


def test_reports_generate_is_deferred_to_background_task() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = ttk.Frame(root)
        parent.pack()
        context = _make_context()
        frame = build_reports_tab(parent, cast(ReportsTabContext, context))
        assert isinstance(frame, ReportsFrame)

        generate_mock = MagicMock(return_value=object())
        frame._controller.generate = generate_mock

        frame._on_generate()

        generate_mock.assert_not_called()
        context._run_background.assert_called_once()
        task = context._run_background.call_args.args[0]
        assert callable(task)
        assert str(frame.generate_button.cget("state")) == tk.DISABLED
        assert str(frame.export_button.cget("state")) == tk.DISABLED
    finally:
        root.destroy()


def test_reports_export_is_deferred_to_background_task() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = ttk.Frame(root)
        parent.pack()
        context = _make_context()
        frame = build_reports_tab(parent, cast(ReportsTabContext, context))
        assert isinstance(frame, ReportsFrame)

        report = SimpleNamespace(filter_by_category=lambda _category: "filtered-report")
        frame._last_result = cast(
            Any,
            SimpleNamespace(
                report=report,
                operations=[],
                filters=SimpleNamespace(wallet_id=None),
            ),
        )
        frame.group_var.set(False)
        frame._set_reports_busy(False)

        with (
            patch(
                "gui.tabs.reports.builder.filedialog.asksaveasfilename",
                return_value="C:\\temp\\report.csv",
            ),
            patch("gui.tabs.reports.builder.report_to_csv") as export_csv,
        ):
            frame._export("csv")

            export_csv.assert_not_called()
            context._run_background.assert_called_once()
            task = context._run_background.call_args.args[0]
            assert callable(task)
            task()
            export_csv.assert_called_once_with(report, "C:\\temp\\report.csv", base_currency="KZT")
    finally:
        root.destroy()
