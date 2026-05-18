from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import TclError
from typing import Any


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


def launch_installer_and_exit(owner: Any, installer_path: str) -> None:
    if not Path(installer_path).is_file():
        raise RuntimeError("The downloaded installer file was not found.")
    try:
        subprocess.Popen([str(installer_path)])
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Failed to launch the downloaded installer.") from exc
    owner.destroy()
