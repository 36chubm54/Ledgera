from __future__ import annotations

import platform
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any, cast

from app_paths import get_icons_dir
from gui.i18n import tr
from gui.ui_theme import bootstrap_ui, get_palette, get_theme


def _bind_dialog_button_navigation(buttons: list[ttk.Button]) -> None:
    if len(buttons) < 2:
        return

    def _focus_button(index: int) -> str:
        buttons[index % len(buttons)].focus_set()
        return "break"

    for index, button in enumerate(buttons):
        button.bind("<Left>", lambda _event, i=index - 1: _focus_button(i), add="+")
        button.bind("<Right>", lambda _event, i=index + 1: _focus_button(i), add="+")
        button.bind("<Up>", lambda _event, i=index - 1: _focus_button(i), add="+")
        button.bind("<Down>", lambda _event, i=index + 1: _focus_button(i), add="+")


def _close_with_break(callback: Callable[[], None]) -> str:
    callback()
    return "break"


def _invoke_if_focused(widget: tk.Misc | None) -> bool:
    if widget is None:
        return False
    focus_widget = widget.winfo_toplevel().focus_get()
    if focus_widget is widget and hasattr(widget, "invoke"):
        widget.invoke()  # type: ignore[attr-defined]
        return True
    return False


def _play_system_sound(kind: str) -> None:
    """
    Plays a system sound appropriate to the message type.
    Supports Windows (winsound) and other OS (tkinter.bell).
    """
    system = platform.system()
    if system == "Windows":
        try:
            import winsound

            sound_map = {
                "error": winsound.MB_ICONHAND,
                "warning": winsound.MB_ICONEXCLAMATION,
                "info": winsound.MB_ICONASTERISK,
            }
            sound_constant = sound_map.get(kind, winsound.MB_OK)
            winsound.MessageBeep(sound_constant)
            return
        except ImportError:
            pass  # falls back to tkinter.bell
    tk.Tk().bell()


def _get_icon_for_kind(kind: str) -> tuple[str, str]:
    """
    Returns an icon for the message type.
    Returns (type, value), where type can be "unicode" or "image".
    If a <kind>.png file exists in project/gui/assets/icons/, returns type "image"
    and the absolute path to the file. Otherwise it returns a Unicode character.
    """
    icons_dir = get_icons_dir()
    icon_file = icons_dir / f"{kind}.png"
    if icon_file.exists():
        return ("image", str(icon_file.resolve()))

    unicode_map = {
        "error": "⛔",
        "warning": "⚠",
        "info": "ℹ",
        "question": "❓",
    }
    symbol = unicode_map.get(kind, "●")
    return ("unicode", symbol)


def _resolve_parent(parent: tk.Misc | None) -> tuple[tk.Tk | tk.Toplevel, tk.Tk | None]:
    if parent is not None:
        # winfo_toplevel() returns Toplevel or Tk, both are subclasses of Misc
        toplevel = parent.winfo_toplevel()
        return cast(tk.Tk | tk.Toplevel, toplevel), None

    default_root = tk._get_default_root()  # type: ignore[attr-defined]
    if default_root is not None:
        toplevel = default_root.winfo_toplevel()
        return cast(tk.Tk | tk.Toplevel, toplevel), None

    temp_root = tk.Tk()
    temp_root.withdraw()
    bootstrap_ui(temp_root, get_theme())
    return temp_root, temp_root


def _center_dialog(
    dialog: tk.Toplevel,
    parent: tk.Misc,
    *,
    min_width: int = 0,
    min_height: int = 0,
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
    dialog.geometry(f"{width}x{height}+{pos_x}+{pos_y}")


def _create_dialog_shell(
    title: str,
    *,
    parent: tk.Misc | None,
    min_width: int,
    min_height: int,
) -> tuple[tk.Toplevel, ttk.Frame, tk.Tk | tk.Toplevel, tk.Tk | None]:
    owner, temp_root = _resolve_parent(parent)
    dialog = tk.Toplevel(owner)
    dialog.withdraw()
    bootstrap_ui(dialog, get_theme())
    palette = get_palette()
    dialog.title(title)
    dialog.transient(owner)
    dialog.configure(background=palette.background)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=16)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)

    _center_dialog(dialog, owner, min_width=min_width, min_height=min_height)
    dialog.deiconify()
    return dialog, content, owner, temp_root


def _run_modal(
    dialog: tk.Toplevel,
    owner: tk.Tk | tk.Toplevel,
    *,
    focus_widget: tk.Misc | None = None,
    temp_root: tk.Tk | None = None,
) -> None:
    try:
        dialog.update_idletasks()
        dialog.grab_set()
        if focus_widget is not None:
            focus_widget.focus_set()
        else:
            dialog.focus_set()
        owner.wait_window(dialog)
    finally:
        if temp_root is not None:
            try:
                temp_root.destroy()
            except tk.TclError:
                pass


def _message_dialog(
    message: str,
    *,
    title: str,
    parent: tk.Misc | None,
    kind: str,
) -> None:
    palette = get_palette()
    tone_map = {
        "error": palette.danger,
        "warning": palette.warning,
        "info": palette.accent_blue,
    }

    base_min_width = 460
    base_min_height = 180

    if len(message) < 60:
        base_min_width = 420
    elif len(message) > 200:
        base_min_width = 540

    dialog, content, owner, temp_root = _create_dialog_shell(
        title,
        parent=parent,
        min_width=base_min_width,
        min_height=base_min_height,
    )
    content.grid_columnconfigure(0, weight=0)
    content.grid_columnconfigure(1, weight=1)
    content.grid_rowconfigure(0, weight=1)
    content.grid_rowconfigure(1, weight=0)

    _play_system_sound(kind)

    icon_type, icon_value = _get_icon_for_kind(kind)
    if icon_type == "unicode":
        icon_label = ttk.Label(
            content,
            text=icon_value,
            font=("Segoe UI", 14),
            foreground=tone_map.get(kind, palette.text_primary),
        )
        icon_label.grid(row=0, column=0, sticky="nw", padx=(0, 16))
    elif icon_type == "image":
        photo = tk.PhotoImage(file=icon_value)
        icon_label = ttk.Label(content, image=photo)
        icon_label.image = photo  # type: ignore
        icon_label.grid(row=0, column=0, sticky="nw", padx=(0, 16))

    wraplength = max(300, base_min_width - 60 - 84)
    body = ttk.Label(content, text=message, justify=tk.LEFT, wraplength=wraplength)
    body.grid(row=0, column=1, sticky="nw", padx=(0, 0), pady=(0, 0))

    button_row = ttk.Frame(content)
    button_row.grid(row=1, column=0, columnspan=2, sticky="s", pady=(16, 0))

    def _close() -> None:
        dialog.destroy()

    def _adjust_height() -> None:
        dialog.update_idletasks()
        content_height = content.winfo_reqheight()
        dialog_height = content_height + 40
        screen_height = dialog.winfo_screenheight()
        max_height = int(screen_height * 0.8)
        if dialog_height > max_height:
            dialog_height = max_height
        current_min_width = base_min_width
        dialog.minsize(current_min_width, dialog_height)
        if dialog.winfo_height() < dialog_height:
            dialog.geometry(f"{dialog.winfo_width()}x{dialog_height}")

    ok_button = ttk.Button(
        button_row,
        text=tr("common.ok", "ОК"),
        style="Primary.TButton",
        command=_close,
    )
    ok_button.grid(row=0, column=0, sticky="s")
    _bind_dialog_button_navigation([ok_button])
    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Escape>", lambda _event: _close_with_break(_close), add="+")
    dialog.bind("<Return>", lambda _event: _close_with_break(ok_button.invoke), add="+")

    dialog.after_idle(_adjust_height)
    _run_modal(dialog, owner, focus_widget=ok_button, temp_root=temp_root)


def show_error(message: str, *, title: str, parent: tk.Misc | None = None) -> None:
    _message_dialog(message, title=title, parent=parent, kind="error")


def show_info(message: str, *, title: str, parent: tk.Misc | None = None) -> None:
    _message_dialog(message, title=title, parent=parent, kind="info")


def show_warning(message: str, *, title: str, parent: tk.Misc | None = None) -> None:
    _message_dialog(message, title=title, parent=parent, kind="warning")


def ask_confirm(
    message: str, *, title: str, parent: tk.Misc | None = None, kind: str = "question"
) -> bool:
    palette = get_palette()
    tone_map = {
        "question": palette.accent_blue,
    }
    result = False
    base_min_width = 500
    base_min_height = 190
    if len(message) < 60:
        base_min_width = 460
    elif len(message) > 200:
        base_min_width = 560

    dialog, content, owner, temp_root = _create_dialog_shell(
        title,
        parent=parent,
        min_width=base_min_width,
        min_height=base_min_height,
    )
    content.grid_columnconfigure(0, weight=0)
    content.grid_columnconfigure(1, weight=1)
    content.grid_rowconfigure(0, weight=1)
    content.grid_rowconfigure(1, weight=0)

    _play_system_sound(kind)

    icon_type, icon_value = _get_icon_for_kind(kind)
    if icon_type == "unicode":
        icon_label = ttk.Label(
            content,
            text=icon_value,
            font=("Segoe UI", 14),
            foreground=tone_map.get(kind, palette.text_primary),
        )
        icon_label.grid(row=0, column=0, sticky="nw", padx=(0, 16))
    elif icon_type == "image":
        photo = tk.PhotoImage(file=icon_value)
        icon_label = ttk.Label(content, image=photo)
        icon_label.image = photo  # type: ignore
        icon_label.grid(row=0, column=0, sticky="nw", padx=(0, 16))

    wraplength = max(300, base_min_width - 60 - 84)
    body = ttk.Label(content, text=message, justify=tk.LEFT, wraplength=wraplength)
    body.grid(row=0, column=1, sticky="nw", padx=(0, 0), pady=(0, 0))

    button_row = ttk.Frame(content)
    button_row.grid(row=1, column=0, columnspan=2, sticky="s", pady=(16, 0))

    def _close(value: bool) -> None:
        nonlocal result
        result = value
        dialog.destroy()

    def _adjust_height() -> None:
        dialog.update_idletasks()
        content_height = content.winfo_reqheight()
        dialog_height = content_height + 40
        screen_height = dialog.winfo_screenheight()
        max_height = int(screen_height * 0.8)
        if dialog_height > max_height:
            dialog_height = max_height
        dialog.minsize(base_min_width, dialog_height)
        if dialog.winfo_height() < dialog_height:
            dialog.geometry(f"{dialog.winfo_width()}x{dialog_height}")

    yes_button = ttk.Button(
        button_row,
        text=tr("common.yes", "Да"),
        style="Primary.TButton",
        command=lambda: _close(True),
    )
    yes_button.grid(row=0, column=0, padx=(0, 8))
    no_button = ttk.Button(
        button_row,
        text=tr("common.no", "Нет"),
        command=lambda: _close(False),
    )
    no_button.grid(row=0, column=1)
    _bind_dialog_button_navigation([yes_button, no_button])

    def _handle_return() -> None:
        if _invoke_if_focused(no_button):
            return
        if _invoke_if_focused(yes_button):
            return
        _close(True)

    dialog.protocol("WM_DELETE_WINDOW", lambda: _close(False))
    dialog.bind("<Escape>", lambda _event: _close_with_break(lambda: _close(False)), add="+")
    dialog.bind("<Return>", lambda _event: _close_with_break(_handle_return), add="+")

    dialog.after_idle(_adjust_height)
    _run_modal(dialog, owner, focus_widget=yes_button, temp_root=temp_root)
    return result


def ask_text(
    title: str,
    prompt: str,
    *,
    parent: tk.Misc | None = None,
    initialvalue: str = "",
    validator: Callable[[str], str | None] | None = None,
    normalize: Callable[[str], str] | None = None,
    ok_text: str | None = None,
    cancel_text: str | None = None,
) -> str | None:
    palette = get_palette()
    result: str | None = None

    base_min_width = 460
    base_min_height = 220
    if len(prompt) < 60:
        base_min_width = 400
    elif len(prompt) > 200:
        base_min_width = 520

    dialog, content, owner, temp_root = _create_dialog_shell(
        title,
        parent=parent,
        min_width=base_min_width,
        min_height=base_min_height,
    )
    content.grid_rowconfigure(3, weight=1)

    wraplength = max(350, base_min_width - 80)
    ttk.Label(content, text=prompt, justify=tk.LEFT, wraplength=wraplength).grid(
        row=1, column=0, sticky="ew", pady=(4, 4)
    )

    value_var = tk.StringVar(value=initialvalue)
    entry = ttk.Entry(content, textvariable=value_var)
    entry.grid(row=2, column=0, sticky="ew")

    status_label = ttk.Label(content, text="", foreground=palette.danger)
    status_label.grid(row=3, column=0, sticky="w")

    button_row = ttk.Frame(content)
    button_row.grid(row=4, column=0, sticky="")

    def _adjust_height() -> None:
        dialog.update_idletasks()
        content_height = content.winfo_reqheight()
        dialog_height = content_height + 40
        screen_height = dialog.winfo_screenheight()
        max_height = int(screen_height * 0.8)
        if dialog_height > max_height:
            dialog_height = max_height
        dialog.minsize(base_min_width, dialog_height)
        if dialog.winfo_height() < dialog_height:
            dialog.geometry(f"{dialog.winfo_width()}x{dialog_height}")

    def _cancel() -> None:
        dialog.destroy()

    def _submit() -> None:
        nonlocal result
        value = value_var.get()
        try:
            if normalize is not None:
                value = normalize(value)
        except (ValueError, TypeError) as error:
            status_label.configure(text=str(error))
            return
        if validator is not None:
            error_text = validator(value)
            if error_text:
                status_label.configure(text=error_text)
                return
        result = value
        dialog.destroy()

    ok_button = ttk.Button(
        button_row,
        text=ok_text or tr("common.ok", "ОК"),
        style="Primary.TButton",
        command=_submit,
    )
    ok_button.grid(row=0, column=0, padx=(0, 8))
    cancel_button = ttk.Button(
        button_row,
        text=cancel_text or tr("common.cancel", "Отмена"),
        command=_cancel,
    )
    cancel_button.grid(row=0, column=1)
    _bind_dialog_button_navigation([ok_button, cancel_button])

    def _handle_return() -> None:
        if _invoke_if_focused(cancel_button):
            return
        if _invoke_if_focused(ok_button):
            return
        _submit()

    dialog.protocol("WM_DELETE_WINDOW", _cancel)
    dialog.bind("<Escape>", lambda _event: _close_with_break(_cancel), add="+")
    dialog.bind("<Return>", lambda _event: _close_with_break(_handle_return), add="+")

    dialog.after_idle(_adjust_height)
    _run_modal(dialog, owner, focus_widget=entry, temp_root=temp_root)
    return result


class _MessageboxCompat:
    def showerror(self, title: str, message: str, *, parent: tk.Misc | None = None) -> None:
        show_error(message, title=title, parent=parent)

    def showinfo(self, title: str, message: str, *, parent: tk.Misc | None = None) -> None:
        show_info(message, title=title, parent=parent)

    def showwarning(self, title: str, message: str, *, parent: tk.Misc | None = None) -> None:
        show_warning(message, title=title, parent=parent)

    def askyesno(self, title: str, message: str, *, parent: tk.Misc | None = None) -> bool:
        return ask_confirm(message, title=title, parent=parent)


class _SimpledialogCompat:
    def askstring(
        self,
        title: str,
        prompt: str,
        *,
        parent: tk.Misc | None = None,
        initialvalue: Any = "",
        **_kwargs: Any,
    ) -> str | None:
        return ask_text(
            title,
            prompt,
            parent=parent,
            initialvalue="" if initialvalue is None else str(initialvalue),
        )


messagebox_compat = _MessageboxCompat()
simpledialog_compat = _SimpledialogCompat()
