from __future__ import annotations

import logging
from dataclasses import dataclass, field
from tkinter import TclError
from unittest.mock import Mock

from gui.shell.core.runtime import run_background_task, set_busy_state


@dataclass
class _Progress:
    calls: list[str] = field(default_factory=list)

    def grid(self) -> None:
        self.calls.append("grid")

    def grid_remove(self) -> None:
        self.calls.append("grid_remove")

    def start(self, interval: int | None = None) -> None:
        self.calls.append(f"start:{interval}")

    def stop(self) -> None:
        self.calls.append("stop")


@dataclass
class _Owner:
    progress: _Progress = field(default_factory=_Progress)
    _busy: bool = False
    titles: list[str] = field(default_factory=list)
    cursors: list[str] = field(default_factory=list)
    disabled: list[bool] = field(default_factory=list)

    def attributes(self, flag: str, value: bool) -> object:
        assert flag == "-disabled"
        self.disabled.append(value)
        return None

    def title(self, text: str) -> object:
        self.titles.append(text)
        return None

    def config(self, **kwargs: object) -> object:
        self.cursors.append(str(kwargs.get("cursor", "")))
        return None


def test_set_busy_state_updates_progress_and_title() -> None:
    owner = _Owner()

    set_busy_state(owner, busy=True, message="Loading", base_title="App")
    set_busy_state(owner, busy=False, message="", base_title="App")

    assert owner._busy is False
    assert owner.disabled == [True, False]
    assert owner.titles == ["App - Loading", "App"]
    assert owner.cursors == ["watch", ""]
    assert owner.progress.calls == ["grid", "start:12", "stop", "grid_remove"]


def test_run_background_task_delegates_to_runtime() -> None:
    runtime = Mock()
    task = Mock(return_value=1)
    on_success = Mock()

    run_background_task(
        runtime,
        task,
        on_success=on_success,
        on_error=None,
        busy_message="busy",
        block_ui=True,
        is_busy=lambda: False,
        set_busy=lambda busy, message: None,
        show_wait_info=lambda token: None,
        show_error=lambda text: None,
        logger=Mock(),
    )

    runtime.run_background.assert_called_once()


def test_set_busy_state_logs_expected_disable_toggle_failure(caplog) -> None:
    @dataclass
    class _BrokenOwner(_Owner):
        def attributes(self, flag: str, value: bool) -> object:
            raise TclError("disable unavailable")

    owner = _BrokenOwner()
    caplog.set_level(logging.DEBUG)

    set_busy_state(owner, busy=True, message="Loading", base_title="App")

    assert "Busy-state window disable toggle skipped" in caplog.text
    assert "disable unavailable" in caplog.text
    assert owner.progress.calls == ["grid", "start:12"]
