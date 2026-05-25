from __future__ import annotations

from types import ModuleType

import main as app_main


def test_run_app_passes_initial_base_currency(monkeypatch) -> None:
    called: list[str] = []

    class FakeSetupOutcome:
        should_launch = True
        initial_base_currency = "USD"

    i18n = ModuleType("gui.i18n")
    i18n.set_language = lambda code: None  # type: ignore[attr-defined]
    shell_window = ModuleType("gui.shell.windowing.window")
    shell_window.enable_windows_dpi_awareness = lambda logger: None  # type: ignore[attr-defined]
    ui_theme = ModuleType("gui.ui_theme")
    ui_theme.set_theme = lambda name: None  # type: ignore[attr-defined]
    initial_setup = ModuleType("gui.initial_setup")
    initial_setup.ensure_initial_setup = lambda: FakeSetupOutcome()  # type: ignore[attr-defined]
    tkinter_gui = ModuleType("gui.tkinter_gui")
    tkinter_gui.main = lambda **kwargs: called.append(  # type: ignore[attr-defined]
        str(kwargs.get("initial_base_currency"))
    )

    monkeypatch.setitem(__import__("sys").modules, "gui.i18n", i18n)
    monkeypatch.setitem(__import__("sys").modules, "gui.shell.windowing.window", shell_window)
    monkeypatch.setitem(__import__("sys").modules, "gui.ui_theme", ui_theme)
    monkeypatch.setitem(__import__("sys").modules, "gui.initial_setup", initial_setup)
    monkeypatch.setitem(__import__("sys").modules, "gui.tkinter_gui", tkinter_gui)

    assert app_main.run_app() is True
    assert called == ["USD"]


def test_run_app_stops_when_initial_setup_is_cancelled(monkeypatch) -> None:
    called: list[str] = []

    class FakeSetupOutcome:
        should_launch = False
        initial_base_currency = None

    i18n = ModuleType("gui.i18n")
    i18n.set_language = lambda code: None  # type: ignore[attr-defined]
    shell_window = ModuleType("gui.shell.windowing.window")
    shell_window.enable_windows_dpi_awareness = lambda logger: None  # type: ignore[attr-defined]
    ui_theme = ModuleType("gui.ui_theme")
    ui_theme.set_theme = lambda name: None  # type: ignore[attr-defined]
    initial_setup = ModuleType("gui.initial_setup")
    initial_setup.ensure_initial_setup = lambda: FakeSetupOutcome()  # type: ignore[attr-defined]
    tkinter_gui = ModuleType("gui.tkinter_gui")
    tkinter_gui.main = lambda **kwargs: called.append("launched")  # type: ignore[attr-defined]

    monkeypatch.setitem(__import__("sys").modules, "gui.i18n", i18n)
    monkeypatch.setitem(__import__("sys").modules, "gui.shell.windowing.window", shell_window)
    monkeypatch.setitem(__import__("sys").modules, "gui.ui_theme", ui_theme)
    monkeypatch.setitem(__import__("sys").modules, "gui.initial_setup", initial_setup)
    monkeypatch.setitem(__import__("sys").modules, "gui.tkinter_gui", tkinter_gui)

    assert app_main.run_app() is False
    assert called == []
