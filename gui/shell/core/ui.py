from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from gui.i18n import set_language
from gui.shell.core.tabs import apply_tab_titles
from gui.shell.owner.preferences import handle_owner_language_change, handle_owner_theme_change
from gui.ui_text import app_title, get_import_formats, get_tab_titles
from gui.ui_theme import DEFAULT_THEME, get_palette, get_theme


def rebuild_owner_status_bar(
    owner: Any,
    *,
    rebuild_status_bar: Callable[..., Any],
    build_status_bar_result: Callable[[Any], Any],
) -> None:
    owner._status_bar = rebuild_status_bar(
        owner,
        build_status_bar_result=build_status_bar_result,
        refresh_status_bar=owner._refresh_status_bar,
    )


def reload_owner_strings(
    owner: Any,
    *,
    rebuild_built_tabs: Callable[[], None],
    rebuild_status_bar: Callable[[], None],
) -> None:
    owner._import_formats = get_import_formats()
    owner.title(app_title())
    if hasattr(owner, "_notebook"):
        apply_tab_titles(
            owner._notebook,
            owner._tab_widgets,
            tab_titles=get_tab_titles(),
        )
    rebuild_status_bar()
    if owner._reload_tabs_pending:
        rebuild_built_tabs()


def schedule_owner_reload_strings(
    owner: Any,
    *,
    rebuild_tabs: bool,
    reload_strings: Callable[[], None],
) -> None:
    owner._reload_tabs_pending = owner._reload_tabs_pending or rebuild_tabs
    if "reload_strings" in owner._after_jobs:
        return

    def _run() -> None:
        reload_strings()

    owner._schedule_after_idle("reload_strings", _run)


def finalize_owner_reload_state(owner: Any) -> bool:
    pending_tabs = owner._reload_tabs_pending
    owner._reload_tabs_pending = False
    return bool(pending_tabs)


def on_owner_language_changed(owner: Any, *, logger: Any) -> bool:
    return handle_owner_language_change(owner, set_language=set_language, logger=logger)


def on_owner_theme_changed(
    owner: Any,
    *,
    bootstrap_ui: Callable[[str], object],
) -> bool:
    return handle_owner_theme_change(owner, bootstrap_ui=bootstrap_ui)


def schedule_owner_notebook_underline(owner: Any) -> None:
    owner._schedule_after_idle("render_notebook_underline", owner._render_notebook_underline)


def render_owner_notebook_underline(owner: Any, *, horizontal_padding: int) -> None:
    if not hasattr(owner, "_notebook") or not hasattr(owner, "_notebook_underline"):
        return
    palette = get_palette()
    try:
        from gui.shell.core.notebook import render_notebook_underline

        render_notebook_underline(
            notebook=owner._notebook,
            canvas=owner._notebook_underline,
            background=palette.background,
            line_color=palette.tab_underline,
            horizontal_padding=horizontal_padding,
        )
    except tk.TclError:
        owner._notebook_underline.place_forget()


def current_theme_name() -> str:
    return get_theme()


def default_theme_name() -> str:
    return DEFAULT_THEME
