from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from gui.ui_helpers import (
    bind_label_wrap,
    enable_treeview_column_autosize,
    normalize_numeric_input,
    safe_destroy,
)


def test_treeview_column_autosize_expands_for_longer_values() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        tree = ttk.Treeview(root, columns=("name", "amount"), show="headings")
        tree.heading("name", text="Name")
        tree.heading("amount", text="Amount")
        tree.column("name", width=80, minwidth=80, anchor="w")
        tree.column("amount", width=60, minwidth=60, anchor="e")
        enable_treeview_column_autosize(tree, max_width=480)
        tree.pack()

        tree.insert("", "end", values=("Short", "10"))
        root.update_idletasks()
        initial_width = int(tree.column("name", "width"))

        tree.insert("", "end", values=("A much longer name than before", "10"))
        root.update_idletasks()

        assert int(tree.column("name", "width")) > initial_width
        assert int(tree.column("name", "width")) >= 80
    finally:
        root.destroy()


def test_treeview_column_autosize_does_not_shrink_by_default() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        tree = ttk.Treeview(root, columns=("name",), show="headings")
        tree.heading("name", text="Name")
        tree.column("name", width=80, minwidth=80, anchor="w")
        enable_treeview_column_autosize(tree, max_width=480)
        tree.pack()

        tree.insert("", "end", iid="1", values=("A much longer name than before",))
        root.update_idletasks()
        grown_width = int(tree.column("name", "width"))

        tree.delete("1")
        tree.insert("", "end", iid="2", values=("Short",))
        root.update_idletasks()

        assert int(tree.column("name", "width")) == grown_width
    finally:
        root.destroy()


def test_treeview_column_autosize_cancels_pending_after_job_on_destroy() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        tree = ttk.Treeview(root, columns=("name",), show="headings")
        tree.heading("name", text="Name")
        tree.column("name", width=80, minwidth=80, anchor="w")
        enable_treeview_column_autosize(tree, max_width=480)
        tree.pack()

        state = getattr(tree, "_column_autosize_state")  # noqa: B009
        assert state is not None
        assert tree.tk.call("after", "info")

        tree.destroy()

        assert not tree.tk.call("after", "info")
    finally:
        root.destroy()


def test_normalize_numeric_input_handles_grouping_and_decimal_separators() -> None:
    assert normalize_numeric_input("15,000") == "15000"
    assert normalize_numeric_input("15 000") == "15000"
    assert normalize_numeric_input("15,5") == "15.5"
    assert normalize_numeric_input("15.5") == "15.5"
    assert normalize_numeric_input("15.000,25") == "15000.25"
    assert normalize_numeric_input("15,000.25") == "15000.25"


def test_safe_destroy_logs_expected_tcl_cleanup_failures(caplog) -> None:
    class DestroyBrokenWidget:
        def destroy(self) -> None:
            raise tk.TclError("already destroyed")

    caplog.set_level(logging.DEBUG)

    safe_destroy(DestroyBrokenWidget())  # type: ignore[arg-type]

    assert "Widget destroy skipped during UI cleanup" in caplog.text
    assert "already destroyed" in caplog.text


def test_bind_label_wrap_logs_expected_wrap_failures(caplog) -> None:
    class BrokenTarget:
        def bind(self, *_args, **_kwargs) -> None:
            return None

        def winfo_width(self) -> int:
            raise RuntimeError("width unavailable")

    class RecordingLabel:
        def __init__(self) -> None:
            self.master = BrokenTarget()

        def configure(self, **_kwargs) -> None:
            raise AssertionError("configure should not run when width lookup fails")

    caplog.set_level(logging.DEBUG)

    bind_label_wrap(RecordingLabel(), padding=32)  # type: ignore[arg-type]

    assert "Label wrap sync skipped during UI refresh" in caplog.text
    assert "width unavailable" in caplog.text
