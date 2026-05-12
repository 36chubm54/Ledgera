from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, cast

from gui.i18n import tr
from gui.ui_dialogs import ask_confirm as _ask_confirm_dialog
from gui.ui_dialogs import ask_text as _ask_text_dialog
from gui.ui_dialogs import show_error as _show_error_dialog
from gui.ui_dialogs import show_info as _show_info_dialog
from gui.ui_dialogs import show_warning as _show_warning_dialog
from gui.ui_theme import get_palette


def show_error(
    message: str,
    *,
    title: str | None = None,
    parent: tk.Misc | None = None,
) -> None:
    resolved_title = title or tr("common.error", "Ошибка")
    _show_error_dialog(message, title=resolved_title, parent=parent)


def show_info(
    message: str,
    *,
    title: str | None = None,
    parent: tk.Misc | None = None,
) -> None:
    resolved_title = title or tr("common.done", "Готово")
    _show_info_dialog(message, title=resolved_title, parent=parent)


def show_warning(
    message: str,
    *,
    title: str | None = None,
    parent: tk.Misc | None = None,
) -> None:
    resolved_title = title or tr("common.warning", "Внимание")
    _show_warning_dialog(message, title=resolved_title, parent=parent)


def ask_confirm(
    message: str,
    *,
    title: str | None = None,
    parent: tk.Misc | None = None,
) -> bool:
    resolved_title = title or tr("common.confirm", "Подтверждение")
    return bool(_ask_confirm_dialog(message, title=resolved_title, parent=parent))


def ask_text(
    title: str,
    prompt: str,
    *,
    parent: tk.Misc | None = None,
    initialvalue: str = "",
    validator=None,
    normalize=None,
    ok_text: str | None = None,
    cancel_text: str | None = None,
) -> str | None:
    return _ask_text_dialog(
        title,
        prompt,
        parent=parent,
        initialvalue=initialvalue,
        validator=validator,
        normalize=normalize,
        ok_text=ok_text,
        cancel_text=cancel_text,
    )


def normalize_numeric_input(value: str) -> str:
    normalized = str(value or "").replace(" ", "").strip()
    if not normalized:
        return normalized
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            return normalized.replace(".", "").replace(",", ".")
        return normalized.replace(",", "")
    if "," in normalized:
        integer_part, fraction = normalized.split(",", 1)
        if len(fraction) == 3 and integer_part.replace("-", "").isdigit() and fraction.isdigit():
            return f"{integer_part}{fraction}"
        return normalized.replace(",", ".")
    return normalized


def parse_numeric_input(value: str) -> float:
    return float(normalize_numeric_input(value))


def ask_numeric_text(
    title: str,
    prompt: str,
    *,
    parent: tk.Misc | None = None,
    initialvalue: str = "",
    validator=None,
    ok_text: str | None = None,
    cancel_text: str | None = None,
) -> str | None:
    def _validate_numeric(value: str) -> str | None:
        try:
            float(value)
        except ValueError:
            return tr("common.error.number_required", "Значение должно быть числом.")
        if validator is None:
            return None
        return validator(value)

    return _ask_text_dialog(
        title,
        prompt,
        parent=parent,
        initialvalue=initialvalue,
        validator=_validate_numeric,
        normalize=normalize_numeric_input,
        ok_text=ok_text,
        cancel_text=cancel_text,
    )


def center_dialog(
    dialog: tk.Toplevel, parent: tk.Misc, *, min_width: int = 0, min_height: int = 0
) -> None:
    dialog.update_idletasks()
    parent_window = parent.winfo_toplevel()
    parent_x = parent_window.winfo_rootx()
    parent_y = parent_window.winfo_rooty()
    parent_w = parent_window.winfo_width()
    parent_h = parent_window.winfo_height()
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    width = min(max(dialog.winfo_reqwidth(), min_width), int(screen_w * 0.92))
    height = min(max(dialog.winfo_reqheight(), min_height), int(screen_h * 0.9))
    pos_x = parent_x + max((parent_w - width) // 2, 0)
    pos_y = parent_y + max((parent_h - height) // 2, 0)
    if min_width or min_height:
        dialog.minsize(min_width or dialog.winfo_reqwidth(), min_height or dialog.winfo_reqheight())
    dialog.resizable(True, True)
    if min_width or min_height:
        dialog.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
    else:
        dialog.geometry(f"{width}x{height}+{pos_x}+{pos_y}")


def set_status(label: ttk.Label, text: str, *, tone: str = "muted") -> None:
    style_map = {
        "muted": "StatusMuted.TLabel",
        "success": "StatusSuccess.TLabel",
        "warning": "StatusWarning.TLabel",
        "danger": "StatusDanger.TLabel",
    }
    label.configure(text=text, style=style_map.get(tone, "StatusMuted.TLabel"))


def create_toolbar(parent: tk.Misc, *, padding: tuple[int, int] = (0, 0)) -> ttk.Frame:
    frame = ttk.Frame(parent, padding=padding)
    frame.grid_columnconfigure(99, weight=1)
    return frame


def create_actions_row(parent: tk.Misc, *, padding: tuple[int, int] = (0, 0)) -> ttk.Frame:
    return ttk.Frame(parent, padding=padding)


def create_canvas_empty_state(canvas: tk.Canvas, text: str) -> None:
    canvas.delete("all")
    width = max(canvas.winfo_width(), 240)
    height = max(canvas.winfo_height(), 140)
    palette = get_palette()
    canvas.create_text(
        width // 2,
        height // 2,
        text=text,
        fill=palette.text_muted,
        font=("Segoe UI", 11),
    )


def attach_treeview_scrollbars(
    parent: tk.Misc,
    tree: ttk.Treeview,
    *,
    row: int,
    column: int,
    horizontal: bool = True,
    padx: int = 0,
    pady: int = 0,
) -> tuple[ttk.Scrollbar, ttk.Scrollbar | None]:
    y_scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    y_scroll.grid(row=row, column=column + 1, sticky="ns", padx=(6, padx), pady=pady)
    tree.configure(yscrollcommand=y_scroll.set)
    x_scroll: ttk.Scrollbar | None = None
    if horizontal:
        x_scroll = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        x_scroll.grid(row=row + 1, column=column, sticky="ew", padx=padx, pady=(6, pady))
        tree.configure(xscrollcommand=x_scroll.set)
    return y_scroll, x_scroll


def enable_treeview_column_autosize(
    tree: ttk.Treeview,
    *,
    columns: tuple[str, ...] | None = None,
    max_width: int = 420,
    cell_padding: int = 24,
    header_padding: int = 28,
    sample_limit: int = 250,
    shrink: bool = False,
) -> ttk.Treeview:
    tree_any = cast(Any, tree)
    state = getattr(tree_any, "_column_autosize_state", None)
    if state is not None:
        schedule = state.get("schedule")
        if callable(schedule):
            schedule()
        return tree

    managed_columns = tuple(columns or tree.cget("columns"))
    if not managed_columns:
        return tree

    style = ttk.Style(tree)

    def _resolve_font(style_name: str, fallback: str) -> tkfont.Font:
        configured = style.lookup(style_name, "font")
        try:
            if configured:
                return tkfont.nametofont(str(configured))
        except (tk.TclError, RuntimeError):
            pass
        return tkfont.Font(font=configured or fallback)

    body_font = _resolve_font("Treeview", "TkDefaultFont")
    heading_font = _resolve_font("Treeview.Heading", "TkHeadingFont")

    def _column_size(column_id: str, option: str, fallback: int = 0) -> int:
        try:
            return int(tree.column(column_id, option))
        except (tk.TclError, RuntimeError, ValueError, TypeError):
            return fallback

    base_widths = {
        column_id: max(
            _column_size(column_id, "width"),
            _column_size(column_id, "minwidth"),
        )
        for column_id in managed_columns
    }
    observed_widths = dict(base_widths)
    pending_job: dict[str, str | None] = {"value": None}
    is_applying = {"value": False}

    def _iter_items(parent: str = ""):
        for item_id in tree.get_children(parent):
            yield item_id
            yield from _iter_items(str(item_id))

    def _measure_text(value: Any, font: tkfont.Font, padding: int) -> int:
        text = str(value or "").replace("\n", " ")
        return font.measure(text) + padding

    def _apply() -> None:
        pending_job["value"] = None
        is_applying["value"] = True
        try:
            if not tree.winfo_exists():
                return
        except (tk.TclError, RuntimeError):
            return

        try:
            for column_id in managed_columns:
                try:
                    current_base = max(
                        base_widths.get(column_id, 0),
                        _column_size(column_id, "minwidth"),
                    )
                    if not shrink:
                        current_base = max(current_base, observed_widths.get(column_id, 0))
                    heading_text = original_heading(column_id, "text")
                    width = max(
                        current_base,
                        _measure_text(heading_text, heading_font, header_padding),
                    )
                    for index, item_id in enumerate(_iter_items()):
                        if index >= sample_limit:
                            break
                        value = (
                            original_item(item_id, "text")
                            if column_id == "#0"
                            else original_set(item_id, column_id)
                        )
                        width = max(width, _measure_text(value, body_font, cell_padding))
                    final_width = min(width, max(current_base, max_width))
                    observed_widths[column_id] = max(
                        observed_widths.get(column_id, 0),
                        final_width,
                    )
                    original_column(column_id, width=final_width)
                except (tk.TclError, RuntimeError):
                    continue
        finally:
            is_applying["value"] = False

    def _schedule(*_args: Any) -> None:
        if pending_job["value"] is not None or is_applying["value"]:
            return
        try:
            pending_job["value"] = tree.after_idle(_apply)
        except (tk.TclError, RuntimeError):
            pending_job["value"] = None

    original_insert = cast(Any, tree.insert)
    original_delete = cast(Any, tree.delete)
    original_item = cast(Any, tree.item)
    original_set = cast(Any, tree.set)
    original_heading = cast(Any, tree.heading)
    original_column = cast(Any, tree.column)

    def _insert(*args: Any, **kwargs: Any):
        result = original_insert(*args, **kwargs)
        _schedule()
        return result

    def _delete(*args: Any) -> None:
        original_delete(*args)
        _schedule()

    def _item(*args: Any, **kwargs: Any):
        result = original_item(*args, **kwargs)
        if kwargs:
            _schedule()
        return result

    def _set(*args: Any, **kwargs: Any):
        result = original_set(*args, **kwargs)
        if len(args) >= 3 or "value" in kwargs:
            _schedule()
        return result

    def _heading(*args: Any, **kwargs: Any):
        result = original_heading(*args, **kwargs)
        if kwargs:
            _schedule()
        return result

    def _column(*args: Any, **kwargs: Any):
        result = original_column(*args, **kwargs)
        if args and kwargs and not is_applying["value"]:
            column_id = str(args[0])
            if column_id in base_widths and ("width" in kwargs or "minwidth" in kwargs):
                base_widths[column_id] = max(
                    _column_size(column_id, "width"),
                    _column_size(column_id, "minwidth"),
                )
                if shrink:
                    observed_widths[column_id] = base_widths[column_id]
                else:
                    observed_widths[column_id] = max(
                        observed_widths.get(column_id, 0),
                        base_widths[column_id],
                    )
            _schedule()
        return result

    tree_any.insert = _insert
    tree_any.delete = _delete
    tree_any.item = _item
    tree_any.set = _set
    tree_any.heading = _heading
    tree_any.column = _column
    tree_any._column_autosize_state = {
        "schedule": _schedule,
        "columns": managed_columns,
        "shrink": shrink,
    }
    tree.bind("<Map>", _schedule, add="+")
    _schedule()
    return tree


def bind_label_wrap(
    label: ttk.Label | tk.Label,
    container: tk.Misc | None = None,
    *,
    padding: int = 32,
    min_width: int = 140,
    max_width: int = 560,
) -> None:
    target = container or label.master
    if target is None:
        return

    def _sync_wrap(_event: tk.Event | None = None) -> None:
        try:
            width = max(min_width, min(max_width, target.winfo_width() - padding))
            label.configure(wraplength=width)
        except (tk.TclError, RuntimeError):
            pass

    target.bind("<Configure>", _sync_wrap, add="+")
    _sync_wrap()
