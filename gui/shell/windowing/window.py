from __future__ import annotations

import ctypes
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import TclError, ttk
from typing import Any

from app_paths import get_linux_package_kind
from gui.i18n import tr

APP_LINUX_WM_CLASS = "Ledgera"
_LINUX_TERMINALS_WITH_SEPARATOR = {
    "gnome-terminal",
    "ptyxis",
}
_LINUX_TERMINALS_WITH_EXEC_REMAINDER = {
    "mate-terminal",
    "xfce4-terminal",
    "konsole",
    "alacritty",
    "xterm",
}
_LINUX_TERMINALS_WITH_EXEC_STRING = {
    "kgx",
    "qterminal",
    "lxterminal",
    "tilix",
    "x-terminal-emulator",
}
_LINUX_TERMINALS_WITH_DIRECT_COMMAND = {
    "kitty",
}
_SUPPORTED_LINUX_TERMINALS = (
    "kgx",
    "gnome-terminal",
    "ptyxis",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "qterminal",
    "lxterminal",
    "tilix",
    "kitty",
    "alacritty",
    "x-terminal-emulator",
    "xterm",
)
_LINUX_TERMINAL_LABELS = {
    "kgx": "Console",
    "gnome-terminal": "GNOME Terminal",
    "ptyxis": "Ptyxis",
    "konsole": "Konsole",
    "xfce4-terminal": "Xfce Terminal",
    "mate-terminal": "MATE Terminal",
    "qterminal": "QTerminal",
    "lxterminal": "LXTerminal",
    "tilix": "Tilix",
    "kitty": "Kitty",
    "alacritty": "Alacritty",
    "x-terminal-emulator": "System Terminal",
    "xterm": "XTerm",
}


def enable_windows_dpi_awareness(logger: logging.Logger) -> None:
    """Enable high-DPI awareness early so Tk and native file dialogs stay sharp."""
    if os.name != "nt":
        return
    errors: list[str] = []

    try:
        user32 = ctypes.windll.user32
    except Exception as exc:
        logger.debug("DPI awareness skipped: user32 is unavailable: %s", exc)
        return

    try:
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            per_monitor_v2 = ctypes.c_void_p(-4)
            if user32.SetProcessDpiAwarenessContext(per_monitor_v2):
                logger.debug("DPI awareness enabled via SetProcessDpiAwarenessContext(PMv2).")
                return
            errors.append("SetProcessDpiAwarenessContext returned 0")
    except Exception as exc:
        errors.append(f"SetProcessDpiAwarenessContext failed: {exc}")

    try:
        shcore = ctypes.windll.shcore
        if hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            logger.debug("DPI awareness enabled via SetProcessDpiAwareness(2).")
            return
        errors.append("SetProcessDpiAwareness is unavailable")
    except Exception as exc:
        errors.append(f"SetProcessDpiAwareness failed: {exc}")

    try:
        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
            logger.debug("DPI awareness enabled via SetProcessDPIAware().")
            return
        errors.append("SetProcessDPIAware is unavailable")
    except Exception as exc:
        errors.append(f"SetProcessDPIAware failed: {exc}")

    if errors:
        logger.warning("DPI awareness was not enabled. Details: %s", " | ".join(errors))


def apply_window_icon(owner: Any, *, icons_dir: Path) -> None:
    ico_path = icons_dir / "app.ico"
    png_path = icons_dir / "app.png"

    try:
        if ico_path.exists():
            owner.iconbitmap(default=str(ico_path))
    except (TclError, OSError):
        pass

    try:
        if png_path.exists():
            app_icon = tk.PhotoImage(file=str(png_path))
            owner.iconphoto(True, app_icon)
            owner._app_icon_ref = app_icon
    except (TclError, OSError):
        pass


def configure_main_window(owner: Any) -> None:
    screen_w = owner.winfo_screenwidth()
    screen_h = owner.winfo_screenheight()
    min_width = min(1640, int(screen_w * 0.9))
    min_height = min(1080, int(screen_h * 0.87))
    owner.geometry(f"{min_width}x{min_height}")
    owner.minsize(min_width, min_height)
    owner.protocol("WM_DELETE_WINDOW", owner.destroy)


def activate_main_window(owner: Any) -> None:
    try:
        owner.deiconify()
    except (AttributeError, TclError):
        pass
    try:
        owner.lift()
    except (AttributeError, TclError):
        pass
    try:
        owner.focus_force()
    except (AttributeError, TclError):
        pass


def _linux_terminal_key(executable_path: str) -> str | None:
    key = Path(executable_path).name.strip().lower()
    if (
        key in _LINUX_TERMINALS_WITH_SEPARATOR
        or key in _LINUX_TERMINALS_WITH_EXEC_REMAINDER
        or key in _LINUX_TERMINALS_WITH_EXEC_STRING
        or key in _LINUX_TERMINALS_WITH_DIRECT_COMMAND
    ):
        return key
    return None


def _resolve_linux_package_manager(package_kind: str) -> str:
    if package_kind == "deb":
        manager = "apt"
    elif package_kind == "rpm":
        manager = "dnf"
    else:
        raise RuntimeError(
            tr(
                "settings.updates.install.error.unknown_linux_package",
                "Не удалось определить тип Linux-пакета для скачанного обновления.",
            )
        )
    if shutil.which(manager):
        return manager
    raise RuntimeError(
        tr(
            "settings.updates.install.error.missing_package_manager",
            "Для установки обновления не найден пакетный менеджер {manager}.",
            manager=manager,
        )
    )


def _build_linux_install_command(artifact_path: str, package_kind: str) -> str:
    normalized_path = str(artifact_path)
    quoted_path = shlex.quote(normalized_path)
    close_prompt = tr(
        "settings.updates.install.terminal_close_prompt",
        "Нажмите Enter, чтобы закрыть терминал...",
    )
    quoted_close_prompt = shlex.quote(f"{close_prompt}\n")
    package_manager = _resolve_linux_package_manager(package_kind)
    return (
        f"sudo {package_manager} install {quoted_path}; "
        "status=$?; "
        f"printf {quoted_close_prompt}; "
        "read _dummy; "
        "exit $status"
    )


def _build_linux_terminal_spawn_args(executable_path: str, shell_command: str) -> list[str]:
    terminal_key = _linux_terminal_key(executable_path)
    if terminal_key is None:
        raise RuntimeError("The selected terminal executable is not supported.")
    if terminal_key in _LINUX_TERMINALS_WITH_SEPARATOR:
        return [executable_path, "--", "sh", "-lc", shell_command]
    if terminal_key in {"mate-terminal", "xfce4-terminal"}:
        return [executable_path, "-x", "sh", "-lc", shell_command]
    if terminal_key in {"konsole", "alacritty", "xterm"}:
        return [executable_path, "-e", "sh", "-lc", shell_command]
    if terminal_key in {"kgx", "qterminal", "lxterminal", "tilix", "x-terminal-emulator"}:
        return [executable_path, "-e", f"sh -lc {shlex.quote(shell_command)}"]
    if terminal_key == "kitty":
        return [executable_path, "sh", "-lc", shell_command]
    raise RuntimeError("The selected terminal executable is not supported.")


def _detect_linux_terminal_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for terminal in _SUPPORTED_LINUX_TERMINALS:
        resolved = shutil.which(terminal)
        if not resolved or resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        label = _LINUX_TERMINAL_LABELS.get(terminal, terminal)
        candidates.append((label, resolved))
    return candidates


def _choose_linux_terminal_executable(
    owner: Any,
    candidates: list[tuple[str, str]],
) -> str | None:
    if not candidates:
        return None

    owner_window = owner.winfo_toplevel()
    dialog = tk.Toplevel(owner_window)
    dialog.withdraw()
    dialog.title(
        tr(
            "settings.updates.terminal_chooser.title",
            "Выбор терминала",
        )
    )
    dialog.transient(owner_window)
    dialog.resizable(False, False)
    dialog.configure(background=owner_window.cget("background"))
    selected_path = tk.StringVar(value=candidates[0][1])
    result: dict[str, str | None] = {"path": None}

    body = ttk.Frame(dialog, padding=16)
    body.grid(row=0, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)

    ttk.Label(
        body,
        text=tr(
            "settings.updates.terminal_chooser.message",
            "Выберите терминал для установки скачанного пакета обновления.",
        ),
        justify="left",
        wraplength=420,
    ).grid(row=0, column=0, sticky="w", pady=(0, 12))

    terminal_list = tk.Listbox(body, height=min(max(len(candidates), 3), 8), exportselection=False)
    terminal_list.grid(row=1, column=0, sticky="ew")
    for index, (label, path) in enumerate(candidates):
        terminal_list.insert(index, f"{label} ({path})")
    terminal_list.selection_set(0)
    terminal_list.activate(0)

    def _sync_selection(_event: object | None = None) -> None:
        selection = terminal_list.curselection()
        if not selection:
            return
        selected_path.set(candidates[int(selection[0])][1])

    terminal_list.bind("<<ListboxSelect>>", _sync_selection)
    terminal_list.bind("<Double-Button-1>", lambda _event: _accept())

    buttons = ttk.Frame(body)
    buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))

    def _accept() -> None:
        _sync_selection()
        result["path"] = str(selected_path.get() or "").strip() or None
        dialog.destroy()

    def _cancel() -> None:
        result["path"] = None
        dialog.destroy()

    ttk.Button(
        buttons,
        text=tr("common.cancel", "Отмена"),
        command=_cancel,
    ).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(
        buttons,
        text=tr("settings.updates.terminal_chooser.use_button", "Использовать"),
        command=_accept,
    ).grid(row=0, column=1)

    dialog.protocol("WM_DELETE_WINDOW", _cancel)
    dialog.update_idletasks()
    width = max(dialog.winfo_reqwidth(), 480)
    height = max(dialog.winfo_reqheight(), 240)
    x = owner_window.winfo_rootx() + max((owner_window.winfo_width() - width) // 2, 0)
    y = owner_window.winfo_rooty() + max((owner_window.winfo_height() - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.deiconify()
    dialog.wait_visibility()
    terminal_list.focus_set()
    dialog.grab_set()
    dialog.wait_window()
    return result["path"]


def _resolve_linux_terminal_executable(
    owner: Any,
    *,
    load_saved_terminal: Callable[[], str | None] | None = None,
    save_terminal: Callable[[str], None] | None = None,
) -> str | None:
    def _validate_terminal_candidate(candidate: str) -> str:
        if not Path(candidate).is_file() or _linux_terminal_key(candidate) is None:
            raise RuntimeError(
                tr(
                    "settings.updates.install.error.unsupported_terminal",
                    "Выбранный терминал не поддерживается для установки обновления.",
                )
            )
        return candidate

    saved_candidate = str(load_saved_terminal() or "").strip() if load_saved_terminal else ""
    if (
        saved_candidate
        and Path(saved_candidate).is_file()
        and _linux_terminal_key(saved_candidate) is not None
    ):
        return saved_candidate
    candidates = _detect_linux_terminal_candidates()
    if len(candidates) == 1:
        return _validate_terminal_candidate(candidates[0][1])
    chosen = _choose_linux_terminal_executable(owner, candidates)
    if not chosen:
        return None
    chosen = _validate_terminal_candidate(chosen)
    if save_terminal is not None:
        save_terminal(chosen)
    return chosen


def launch_downloaded_update_and_exit(
    owner: Any,
    artifact_path: str,
    *,
    load_saved_terminal: Callable[[], str | None] | None = None,
    save_terminal: Callable[[str], None] | None = None,
    mark_pending_cleanup: Callable[[str, str], None] | None = None,
    target_version: str | None = None,
) -> None:
    if not Path(artifact_path).is_file():
        raise RuntimeError(
            tr(
                "settings.updates.install.error.missing_download",
                "Скачанный файл обновления не найден.",
            )
        )
    try:
        if mark_pending_cleanup is not None and target_version:
            mark_pending_cleanup(str(artifact_path), target_version)
        if os.name == "nt":
            subprocess.Popen([str(artifact_path)])
        elif sys.platform.startswith("linux"):
            package_kind = get_linux_package_kind()
            if package_kind not in {"deb", "rpm"}:
                raise RuntimeError(
                    tr(
                        "settings.updates.install.error.unknown_linux_package",
                        "Не удалось определить тип Linux-пакета для скачанного обновления.",
                    )
                )
            terminal_executable = _resolve_linux_terminal_executable(
                owner,
                load_saved_terminal=load_saved_terminal,
                save_terminal=save_terminal,
            )
            if not terminal_executable:
                raise RuntimeError(
                    tr(
                        "settings.updates.install.error.no_supported_terminal",
                        "Не найден поддерживаемый терминал для установки обновления.",
                    )
                )
            subprocess.Popen(
                _build_linux_terminal_spawn_args(
                    terminal_executable,
                    _build_linux_install_command(artifact_path, package_kind),
                )
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(artifact_path)])
        else:
            raise RuntimeError(
                tr(
                    "settings.updates.install.error.unsupported_platform",
                    "Открытие скачанного файла обновления не поддерживается на этой платформе.",
                )
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            tr(
                "settings.updates.install.error.open_failed",
                "Не удалось открыть скачанный файл обновления.",
            )
        ) from exc
    owner.destroy()


def launch_installer_and_exit(owner: Any, installer_path: str) -> None:
    launch_downloaded_update_and_exit(owner, installer_path)
