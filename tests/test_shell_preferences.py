from __future__ import annotations

import logging
from types import SimpleNamespace

from gui.shell.shell_preferences import (
    apply_display_currency_change,
    apply_language_change,
    apply_theme_change,
    handle_owner_display_currency_change,
    handle_owner_language_change,
    handle_owner_theme_change,
    reload_ui_strings,
)


def test_apply_language_change_saves_and_schedules_reload() -> None:
    called: list[str] = []

    changed = apply_language_change(
        selected="en",
        current_language="ru",
        set_language=lambda value: called.append(f"set:{value}"),
        save_language_preference=lambda value: called.append(f"save:{value}"),
        schedule_reload_strings=lambda: called.append("reload"),
        logger=logging.getLogger("test"),
    )

    assert changed is True
    assert called == ["set:en", "save:en", "reload"]


def test_apply_language_change_ignores_same_language() -> None:
    called: list[str] = []

    changed = apply_language_change(
        selected="ru",
        current_language="ru",
        set_language=lambda value: called.append(f"set:{value}"),
        save_language_preference=lambda value: called.append(f"save:{value}"),
        schedule_reload_strings=lambda: called.append("reload"),
        logger=logging.getLogger("test"),
    )

    assert changed is False
    assert called == []


def test_apply_theme_change_runs_full_theme_pipeline() -> None:
    called: list[str] = []

    changed = apply_theme_change(
        selected_label="Темная",
        theme_label_to_key={"Светлая": "light", "Темная": "dark"},
        current_theme="light",
        default_theme="light",
        bootstrap_ui=lambda theme: called.append(f"bootstrap:{theme}"),
        schedule_notebook_underline=lambda: called.append("underline"),
        save_theme_preference=lambda theme: called.append(f"save:{theme}"),
        refresh_theme_surfaces=lambda: called.append("refresh"),
    )

    assert changed is True
    assert called == ["bootstrap:dark", "underline", "save:dark", "refresh"]


def test_apply_display_currency_change_refreshes_views() -> None:
    called: list[str] = []

    changed = apply_display_currency_change(
        selected="usd",
        current_display_currency="KZT",
        set_display_currency=lambda code: called.append(f"set:{code}"),
        refresh_display_currency_views=lambda: called.append("views"),
        refresh_status_bar=lambda: called.append("status"),
    )

    assert changed is True
    assert called == ["set:USD", "views", "status"]


def test_reload_ui_strings_runs_full_reload_pipeline() -> None:
    called: list[str] = []

    reload_ui_strings(
        set_import_formats=lambda: called.append("formats"),
        set_title=lambda title: called.append(f"title:{title}"),
        title_text="App",
        apply_tab_titles=lambda: called.append("tabs"),
        rebuild_status_bar=lambda: called.append("status"),
        rebuild_tabs=True,
        rebuild_built_tabs=lambda: called.append("rebuild"),
    )

    assert called == ["formats", "title:App", "tabs", "status", "rebuild"]


def test_owner_preference_handlers_delegate_to_owner_state(monkeypatch) -> None:
    called: list[str] = []
    owner = SimpleNamespace(
        controller=SimpleNamespace(
            save_language_preference=lambda value: called.append(f"save-lang:{value}"),
            save_theme_preference=lambda value: called.append(f"save-theme:{value}"),
            get_display_currency=lambda: "KZT",
            set_display_currency=lambda value: called.append(f"set-display:{value}"),
        ),
        _language_var=SimpleNamespace(get=lambda: "EN"),
        _theme_var=SimpleNamespace(get=lambda: "Темная"),
        _theme_label_to_key={"Темная": "dark"},
        _display_currency_var=SimpleNamespace(get=lambda: "usd"),
        _schedule_reload_strings=lambda *, rebuild_tabs=False: called.append(
            f"reload:{rebuild_tabs}"
        ),
        _schedule_notebook_underline=lambda: called.append("underline"),
        _refresh_theme_surfaces=lambda: called.append("refresh-theme"),
        _refresh_display_currency_views=lambda: called.append("refresh-display"),
        _refresh_status_bar=lambda: called.append("refresh-status"),
    )
    monkeypatch.setattr("gui.shell.shell_preferences.get_language", lambda: "ru")
    monkeypatch.setattr("gui.shell.shell_preferences.get_theme", lambda: "light")

    assert handle_owner_language_change(
        owner,
        set_language=lambda value: called.append(f"set-lang:{value}"),
        logger=logging.getLogger("test"),
    )
    assert handle_owner_theme_change(
        owner,
        bootstrap_ui=lambda theme: called.append(f"bootstrap:{theme}"),
    )
    assert handle_owner_display_currency_change(owner)

    assert "set-lang:en" in called
    assert "bootstrap:dark" in called
    assert "set-display:USD" in called
