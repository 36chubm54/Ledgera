from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from gui.i18n import get_language
from gui.ui_theme import DEFAULT_THEME, get_theme


def apply_language_change(
    *,
    selected: str,
    current_language: str,
    set_language: Callable[[str], object],
    save_language_preference: Callable[[str], object],
    schedule_reload_strings: Callable[[], object],
    logger: logging.Logger,
) -> bool:
    normalized = str(selected or "").strip().lower()
    if not normalized or normalized == current_language:
        return False
    try:
        set_language(normalized)
    except ValueError:
        logger.warning("Unsupported language selected: %s", normalized)
        return False
    save_language_preference(normalized)
    schedule_reload_strings()
    return True


def apply_theme_change(
    *,
    selected_label: str,
    theme_label_to_key: dict[str, str],
    current_theme: str,
    default_theme: str,
    bootstrap_ui: Callable[[str], object],
    schedule_notebook_underline: Callable[[], object],
    save_theme_preference: Callable[[str], object],
    refresh_theme_surfaces: Callable[[], object],
) -> bool:
    selected_theme = theme_label_to_key.get(str(selected_label or ""), default_theme)
    if selected_theme == current_theme:
        return False
    bootstrap_ui(selected_theme)
    schedule_notebook_underline()
    save_theme_preference(selected_theme)
    refresh_theme_surfaces()
    return True


def apply_display_currency_change(
    *,
    selected: str,
    current_display_currency: str,
    set_display_currency: Callable[[str], Any],
    refresh_display_currency_views: Callable[[], Any],
    refresh_status_bar: Callable[[], Any],
) -> bool:
    normalized = str(selected or "").strip().upper()
    if not normalized or normalized == current_display_currency:
        return False
    set_display_currency(normalized)
    refresh_display_currency_views()
    refresh_status_bar()
    return True


def reload_ui_strings(
    *,
    set_import_formats: Callable[[], Any],
    set_title: Callable[[str], Any],
    title_text: str,
    apply_tab_titles: Callable[[], Any],
    rebuild_status_bar: Callable[[], Any],
    rebuild_tabs: bool,
    rebuild_built_tabs: Callable[[], Any],
) -> None:
    set_import_formats()
    set_title(title_text)
    apply_tab_titles()
    rebuild_status_bar()
    if rebuild_tabs:
        rebuild_built_tabs()


def handle_owner_language_change(
    owner: Any,
    *,
    set_language: Callable[[str], object],
    logger: logging.Logger,
) -> bool:
    if owner._language_var is None:
        return False
    return apply_language_change(
        selected=str(owner._language_var.get() or ""),
        current_language=get_language(),
        set_language=set_language,
        save_language_preference=owner.controller.save_language_preference,
        schedule_reload_strings=lambda: owner._schedule_reload_strings(rebuild_tabs=True),
        logger=logger,
    )


def handle_owner_theme_change(
    owner: Any,
    *,
    bootstrap_ui: Callable[[str], object],
) -> bool:
    if owner._theme_var is None:
        return False
    return apply_theme_change(
        selected_label=str(owner._theme_var.get() or ""),
        theme_label_to_key=owner._theme_label_to_key,
        current_theme=get_theme(),
        default_theme=DEFAULT_THEME,
        bootstrap_ui=bootstrap_ui,
        schedule_notebook_underline=owner._schedule_notebook_underline,
        save_theme_preference=owner.controller.save_theme_preference,
        refresh_theme_surfaces=owner._refresh_theme_surfaces,
    )


def handle_owner_display_currency_change(owner: Any) -> bool:
    if owner._display_currency_var is None:
        return False
    return apply_display_currency_change(
        selected=str(owner._display_currency_var.get() or ""),
        current_display_currency=owner.controller.get_display_currency(),
        set_display_currency=owner.controller.set_display_currency,
        refresh_display_currency_views=owner._refresh_display_currency_views,
        refresh_status_bar=owner._refresh_status_bar,
    )
