from __future__ import annotations

from dataclasses import dataclass

from gui.shell.core.lifecycle import ensure_tab_built, handle_tab_changed, schedule_deferred_action


@dataclass
class _Notebook:
    selected_value: object

    def select(self, tab_id: object | None = None) -> object:
        if tab_id is not None:
            self.selected_value = tab_id
        return self.selected_value


def test_ensure_tab_built_adds_new_tab_once() -> None:
    built_tabs = {"operations"}
    built_calls: list[str] = []

    added = ensure_tab_built(
        built_tabs,
        "reports",
        build_tab_for_key=lambda key: built_calls.append(key) or True,
    )
    skipped = ensure_tab_built(
        built_tabs,
        "reports",
        build_tab_for_key=lambda key: built_calls.append(key) or True,
    )

    assert added is True
    assert skipped is False
    assert built_calls == ["reports"]
    assert built_tabs == {"operations", "reports"}


def test_handle_tab_changed_builds_selected_tab_and_schedules_underline() -> None:
    notebook = _Notebook("widget:reports")
    built: list[str] = []
    calls: list[str] = []

    handle_tab_changed(
        notebook,
        {"widget:reports": "reports"},
        ensure_tab_built_for_key=lambda key: built.append(key),
        schedule_notebook_underline=lambda: calls.append("underline"),
    )

    assert built == ["reports"]
    assert calls == ["underline"]


def test_schedule_deferred_action_delegates_to_runtime_scheduler() -> None:
    scheduled: list[tuple[str, object]] = []

    result = schedule_deferred_action(
        lambda key, callback: scheduled.append((key, callback)) or "job-id",
        "startup_refresh",
        lambda: None,
    )

    assert result == "job-id"
    assert scheduled and scheduled[0][0] == "startup_refresh"
