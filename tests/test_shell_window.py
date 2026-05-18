from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gui.shell.shell_window import configure_main_window, launch_installer_and_exit


class _FakeWindow:
    def __init__(self) -> None:
        self.geometry_value: str | None = None
        self.minsize_value: tuple[int, int] | None = None
        self.protocol_calls: list[tuple[str, object]] = []
        self.destroyed = False

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def geometry(self, value: str) -> None:
        self.geometry_value = value

    def minsize(self, width: int, height: int) -> None:
        self.minsize_value = (width, height)

    def protocol(self, name: str, callback: object) -> None:
        self.protocol_calls.append((name, callback))

    def destroy(self) -> None:
        self.destroyed = True
        return None


def test_configure_main_window_sets_geometry_and_protocol() -> None:
    window = _FakeWindow()

    configure_main_window(window)

    assert window.geometry_value == "1640x939"
    assert window.minsize_value == (1640, 939)
    assert window.protocol_calls and window.protocol_calls[0][0] == "WM_DELETE_WINDOW"


def test_launch_installer_and_exit_spawns_process_and_closes_window(monkeypatch) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_installer_and_exit(window, "C:\\temp\\FinAccountingApp-2.0.2-setup.exe")

    assert calls == [["C:\\temp\\FinAccountingApp-2.0.2-setup.exe"]]
    assert window.destroyed is True


def test_launch_installer_and_exit_raises_when_spawn_fails(monkeypatch) -> None:
    window = _FakeWindow()
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def _raise(_args):
        raise OSError("denied")

    monkeypatch.setattr(subprocess, "Popen", _raise)

    with pytest.raises(RuntimeError):
        launch_installer_and_exit(window, "C:\\temp\\FinAccountingApp-2.0.2-setup.exe")


def test_launch_installer_and_exit_raises_when_installer_missing(tmp_path: Path) -> None:
    window = _FakeWindow()

    with pytest.raises(RuntimeError):
        launch_installer_and_exit(window, str(tmp_path / "missing-setup.exe"))

    assert window.destroyed is False
