from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gui.shell.windowing.window import (
    configure_main_window,
    launch_downloaded_update_and_exit,
    launch_installer_and_exit,
)


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

    launch_installer_and_exit(window, "C:\\temp\\Ledgera-2.0.2-setup.exe")

    assert calls == [["C:\\temp\\Ledgera-2.0.2-setup.exe"]]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_uses_terminal_for_deb_linux(monkeypatch) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    cleanup_markers: list[tuple[str, str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr("gui.shell.windowing.window.shutil.which", lambda name: "/usr/bin/kgx")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_downloaded_update_and_exit(
        window,
        "/tmp/Ledgera-2.0.2-x86_64.deb",
        mark_pending_cleanup=lambda path, version: cleanup_markers.append((path, version)),
        target_version="2.0.2",
    )

    assert calls
    assert calls[0][:4] == ["/usr/bin/kgx", "--", "sh", "-lc"]
    assert "sudo apt install /tmp/Ledgera-2.0.2-x86_64.deb" in calls[0][4]
    assert cleanup_markers == [("/tmp/Ledgera-2.0.2-x86_64.deb", "2.0.2")]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_requires_apt_for_deb_linux(monkeypatch) -> None:
    window = _FakeWindow()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(
        "gui.shell.windowing.window.shutil.which",
        lambda name: "/usr/bin/kgx" if name == "kgx" else None,
    )

    with pytest.raises(RuntimeError, match="apt"):
        launch_downloaded_update_and_exit(window, "/tmp/Ledgera-2.0.2-x86_64.deb")

    assert window.destroyed is False


def test_launch_downloaded_update_and_exit_uses_terminal_for_rpm_linux(monkeypatch) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "rpm")
    monkeypatch.setattr("gui.shell.windowing.window.shutil.which", lambda name: "/usr/bin/konsole")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_downloaded_update_and_exit(window, "/tmp/Ledgera-2.0.2-x86_64.rpm")

    assert calls
    assert calls[0][:4] == ["/usr/bin/konsole", "-e", "sh", "-lc"]
    assert "sudo dnf install /tmp/Ledgera-2.0.2-x86_64.rpm" in calls[0][4]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_uses_saved_terminal_preference(monkeypatch) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(
        "gui.shell.windowing.window.shutil.which",
        lambda name: "/usr/bin/apt" if name == "apt" else None,
    )
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_downloaded_update_and_exit(
        window,
        "/tmp/Ledgera-2.0.2-x86_64.deb",
        load_saved_terminal=lambda: "/usr/bin/qterminal",
    )

    assert calls
    assert calls[0][:4] == ["/usr/bin/qterminal", "-e", "sh", "-lc"]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_supports_x_terminal_emulator(monkeypatch) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(
        "gui.shell.windowing.window.shutil.which",
        lambda name: (
            "/usr/bin/x-terminal-emulator"
            if name == "x-terminal-emulator"
            else "/usr/bin/apt"
            if name == "apt"
            else None
        ),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_downloaded_update_and_exit(window, "/tmp/Ledgera-2.0.2-x86_64.deb")

    assert calls
    assert calls[0][:4] == ["/usr/bin/x-terminal-emulator", "-e", "sh", "-lc"]
    assert "sudo apt install /tmp/Ledgera-2.0.2-x86_64.deb" in calls[0][4]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_saves_supported_terminal_from_chooser(
    monkeypatch,
) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    saved: list[str] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(
        "gui.shell.windowing.window._detect_linux_terminal_candidates",
        lambda: [
            ("Console", "/usr/bin/kgx"),
            ("Xfce Terminal", "/usr/bin/xfce4-terminal"),
        ],
    )
    monkeypatch.setattr(
        "gui.shell.windowing.window._choose_linux_terminal_executable",
        lambda owner, candidates: "/usr/bin/xfce4-terminal",
    )
    monkeypatch.setattr("gui.shell.windowing.window.shutil.which", lambda name: "/usr/bin/apt")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    launch_downloaded_update_and_exit(
        window,
        "/tmp/Ledgera-2.0.2-x86_64.deb",
        load_saved_terminal=lambda: None,
        save_terminal=lambda path: saved.append(path),
    )

    assert calls
    assert calls[0][:4] == ["/usr/bin/xfce4-terminal", "--", "sh", "-lc"]
    assert saved == ["/usr/bin/xfce4-terminal"]
    assert window.destroyed is True


def test_launch_downloaded_update_and_exit_rejects_unsupported_terminal_choice(
    monkeypatch,
) -> None:
    window = _FakeWindow()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "posix")
    monkeypatch.setattr("gui.shell.windowing.window.sys.platform", "linux")
    monkeypatch.setattr("gui.shell.windowing.window.get_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(
        "gui.shell.windowing.window._detect_linux_terminal_candidates",
        lambda: [("Custom", "/usr/bin/custom-terminal")],
    )

    with pytest.raises(RuntimeError, match="не поддерживается|not supported"):
        launch_downloaded_update_and_exit(window, "/tmp/Ledgera-2.0.2-x86_64.deb")

    assert window.destroyed is False


def test_launch_installer_and_exit_raises_when_spawn_fails(monkeypatch) -> None:
    window = _FakeWindow()
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def _raise(_args):
        raise OSError("denied")

    monkeypatch.setattr(subprocess, "Popen", _raise)

    with pytest.raises(RuntimeError):
        launch_installer_and_exit(window, "C:\\temp\\Ledgera-2.0.2-setup.exe")


def test_launch_installer_and_exit_raises_when_installer_missing(tmp_path: Path) -> None:
    window = _FakeWindow()

    with pytest.raises(RuntimeError):
        launch_installer_and_exit(window, str(tmp_path / "missing-setup.exe"))

    assert window.destroyed is False


def test_launch_downloaded_update_and_exit_does_not_spawn_when_cleanup_marker_fails(
    monkeypatch,
) -> None:
    window = _FakeWindow()
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr("gui.shell.windowing.window.os.name", "nt")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(list(args)))

    with pytest.raises(RuntimeError, match="marker failed"):
        launch_downloaded_update_and_exit(
            window,
            "C:\\temp\\Ledgera-2.0.2-setup.exe",
            mark_pending_cleanup=lambda _path, _version: (_ for _ in ()).throw(
                RuntimeError("marker failed")
            ),
            target_version="2.0.2",
        )

    assert calls == []
    assert window.destroyed is False
